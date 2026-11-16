"""Version-aware (temporal) retrieval helpers and proposed-vs-final diffs.

Semantics for a regulatory lineage on an `as_of` date:
  * the *current version* is the latest document published on or before as_of;
  * its *legal status* is one of: proposed, adopted_not_effective, effective, statute_pending;
  * a later document in the lineage is never visible (no look-ahead).
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from ledgerline.corpus.manifest import CorpusDoc, Manifest
from ledgerline.ingest.models import Chunk

Status = Literal[
    "not_yet_published", "proposed", "adopted_not_effective", "effective", "superseded"
]


@dataclass
class VersionStatus:
    lineage_id: str
    as_of: date
    doc_id: str | None
    title: str | None
    status: Status
    publication_date: date | None = None
    effective_date: date | None = None
    superseded_by: str | None = None
    history: list[str] = field(default_factory=list)

    def describe(self) -> str:
        if self.doc_id is None:
            return f"No version of {self.lineage_id} had been published as of {self.as_of}."
        s = {
            "proposed": "a proposed rule (not binding)",
            "adopted_not_effective": f"adopted but not yet effective (effective "
            f"{self.effective_date})",
            "effective": f"in effect since {self.effective_date}",
            "superseded": "superseded",
            "not_yet_published": "not yet published",
        }[self.status]
        return (
            f"As of {self.as_of}, the governing version of {self.lineage_id} is "
            f"{self.doc_id} (published {self.publication_date}), which is {s}."
        )


def version_as_of(manifest: Manifest, lineage_id: str, as_of: date) -> VersionStatus:
    docs = sorted(
        (d for d in manifest.docs if d.lineage_id == lineage_id),
        key=lambda d: d.publication_date or date.min,
    )
    visible = [d for d in docs if d.publication_date is None or d.publication_date <= as_of]
    if not visible:
        return VersionStatus(lineage_id, as_of, None, None, "not_yet_published")
    cur: CorpusDoc = visible[-1]
    if cur.doc_type == "proposed_rule":
        status: Status = "proposed"
    elif cur.effective_date and cur.effective_date > as_of:
        status = "adopted_not_effective"
    else:
        status = "effective"
    return VersionStatus(
        lineage_id,
        as_of,
        cur.doc_id,
        cur.title,
        status,
        cur.publication_date,
        cur.effective_date,
        history=[d.doc_id for d in visible[:-1]],
    )


def visible_on(chunk: Chunk, as_of: date) -> bool:
    """Chunk-level visibility, mirroring the Qdrant payload filter in store.build_filter."""
    if chunk.valid_from and chunk.valid_from > as_of:
        return False
    return not (chunk.valid_to and chunk.valid_to <= as_of)


# ---------------------------------------------------------------------------------------
# diff_versions

_SECTION = re.compile(r"^(\d+\.\d+[a-z]?)")


@dataclass
class ClauseChange:
    section: str
    change: Literal["added", "removed", "modified", "unchanged"]
    similarity: float
    old_text: str = ""
    new_text: str = ""
    old_cite: str | None = None
    new_cite: str | None = None
    diff: list[str] = field(default_factory=list)


@dataclass
class VersionDiff:
    lineage_id: str
    old_doc: str
    new_doc: str
    changes: list[ClauseChange]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for c in self.changes:
            out[c.change] += 1
        return dict(out)


def _by_section(chunks: list[Chunk]) -> dict[str, list[Chunk]]:
    out: dict[str, list[Chunk]] = defaultdict(list)
    for c in chunks:
        if not c.clause:
            continue
        m = _SECTION.match(c.clause)
        if m:
            out[m.group(1)].append(c)
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def diff_versions(
    chunks: list[Chunk],
    old_doc: str,
    new_doc: str,
    lineage_id: str = "",
    modified_threshold: float = 0.97,
) -> VersionDiff:
    old = _by_section([c for c in chunks if c.doc_id == old_doc])
    new = _by_section([c for c in chunks if c.doc_id == new_doc])
    changes: list[ClauseChange] = []
    for sec in sorted(set(old) | set(new), key=_sort_key):
        o = _norm(" ".join(c.text for c in old.get(sec, [])))
        n = _norm(" ".join(c.text for c in new.get(sec, [])))
        oc = f"[doc:{old_doc}#s{sec}]" if sec in old else None
        nc = f"[doc:{new_doc}#s{sec}]" if sec in new else None
        if not o:
            changes.append(ClauseChange(sec, "added", 0.0, new_text=n, new_cite=nc))
            continue
        if not n:
            changes.append(ClauseChange(sec, "removed", 0.0, old_text=o, old_cite=oc))
            continue
        sm = difflib.SequenceMatcher(None, o.split(), n.split(), autojunk=False)
        ratio = sm.ratio()
        kind: Literal["modified", "unchanged"] = (
            "unchanged" if ratio >= modified_threshold else "modified"
        )
        diff = []
        if kind == "modified":
            ow, nw = o.split(), n.split()
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                if tag in ("delete", "replace"):
                    diff.append("- " + " ".join(ow[i1:i2])[:300])
                if tag in ("insert", "replace"):
                    diff.append("+ " + " ".join(nw[j1:j2])[:300])
        changes.append(ClauseChange(sec, kind, round(ratio, 3), o, n, oc, nc, diff[:12]))
    return VersionDiff(lineage_id, old_doc, new_doc, changes)


def _sort_key(sec: str) -> tuple[int, int, str]:
    m = re.match(r"(\d+)\.(\d+)([a-z]?)", sec)
    return (int(m.group(1)), int(m.group(2)), m.group(3)) if m else (0, 0, sec)
