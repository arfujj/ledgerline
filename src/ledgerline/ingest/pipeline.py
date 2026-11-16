"""Ingestion pipeline: parse -> scan -> chunk (structured + naive) -> JSONL artifacts.

Parsed sections are cached per file content hash, so re-runs skip Docling entirely.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path

from ledgerline.core.paths import guard_read, iter_dataroom
from ledgerline.corpus.manifest import Manifest
from ledgerline.guardrails.injection import scan_document, score_text
from ledgerline.ingest import docling_parser, regs
from ledgerline.ingest.chunking import chunk_sections, naive_chunks
from ledgerline.ingest.models import Chunk, DocMeta, Section

log = logging.getLogger(__name__)
DOC_EXTS = {".pdf", ".docx", ".md"}
SKIP_NAMES = {"README.md"}
FOLDER_TYPES = {
    "policies": "policy",
    "sops": "sop",
    "contracts": "contract",
    "board": "board_deck",
    "postmortems": "postmortem",
    "org": "org",
    "registers": "register",
    "memos": "memo",
    "audit": "memo",
}
REDACTED = "[REDACTED: suspected prompt-injection content quarantined at ingest]"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ParseCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def get(self, sha: str) -> tuple[list[Section], dict[str, str]] | None:
        p = self.root / f"{sha}.json"
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        return [Section.model_validate(s) for s in data["sections"]], data["meta"]

    def put(self, sha: str, sections: list[Section], meta: dict[str, str]) -> None:
        (self.root / f"{sha}.json").write_text(
            json.dumps({"sections": [s.model_dump() for s in sections], "meta": meta})
        )


def _parse_regulatory(path: Path, doc_id: str) -> list[Section]:
    if doc_id.startswith("FR-"):
        return regs.parse_fr_xml(path)
    if doc_id.startswith("CFR-"):
        return regs.parse_ecfr_xml(path)
    if path.suffix in (".html", ".htm") and "PLAW" in path.read_text(errors="ignore")[:5000]:
        return regs.parse_public_law_html(path)
    if doc_id.startswith("GENIUS"):
        return regs.parse_public_law_html(path)
    return docling_parser.parse(path)[0]


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


class IngestResult:
    def __init__(self) -> None:
        self.docs: list[DocMeta] = []
        self.chunks: list[Chunk] = []
        self.naive: list[Chunk] = []
        self.quarantine: list[dict[str, object]] = []


def _apply_scan(meta: DocMeta, chunks: list[Chunk], path: Path, res: IngestResult) -> None:
    full = "\n".join(c.text for c in chunks)
    scan = scan_document(path, full)
    if not scan.flagged:
        return
    res.quarantine.append(
        {
            "doc_id": meta.doc_id,
            "path": meta.source_path,
            "score": scan.score,
            "signals": scan.signals,
            "evidence": scan.evidence[:5],
        }
    )
    for c in chunks:
        c.trusted = False
        c.injection_flags = sorted({s.split(":")[-1] for s in scan.signals})
        score, _, _ = score_text(c.text)
        if score > 0:
            c.text = REDACTED


def ingest_dataroom(root: Path, cache: ParseCache, res: IngestResult) -> None:
    for path in iter_dataroom(root):
        if path.suffix.lower() not in DOC_EXTS or path.name in SKIP_NAMES:
            continue
        guard_read(path.relative_to(root))
        sha = _sha(path)
        hit = cache.get(sha)
        if hit is None:
            hit = docling_parser.parse(path)
            cache.put(sha, *hit)
        sections, hdr = hit
        folder = path.relative_to(root).parts[0]
        meta = DocMeta(
            doc_id=hdr.get("doc_id", path.stem),
            corpus="dataroom",
            title=hdr.get("title", path.stem),
            doc_type=FOLDER_TYPES.get(folder, "document"),
            issuer=f"NovaPay (client); owner: {hdr.get('owner', 'unknown')}",
            version=hdr.get("version", ""),
            effective_date=_d(hdr.get("effective")),
            valid_from=_d(hdr.get("effective")),
            source_path=str(path),
            sha256=sha,
        )
        chunks = chunk_sections(meta, sections)
        _apply_scan(meta, chunks, path, res)
        res.docs.append(meta)
        res.chunks += chunks
        res.naive += naive_chunks(meta, sections)


def ingest_regulatory(root: Path, cache: ParseCache, res: IngestResult) -> None:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        log.warning("No regulatory manifest at %s; skipping", manifest_path)
        return
    for d in Manifest.load(manifest_path).docs:
        path = root / d.local_path
        sha = _sha(path)
        hit = cache.get(sha)
        if hit is None:
            hit = (_parse_regulatory(path, d.doc_id), {})
            cache.put(sha, *hit)
        sections, _ = hit
        meta = DocMeta(
            doc_id=d.doc_id,
            corpus="regulatory",
            title=d.title,
            doc_type=d.doc_type,
            issuer=d.issuer,
            version=d.fr_document_number
            or (d.publication_date.isoformat() if d.publication_date else ""),
            effective_date=d.effective_date,
            publication_date=d.publication_date,
            valid_from=d.valid_from,
            valid_to=d.valid_to,
            lineage_id=d.lineage_id,
            source_path=str(path),
            source_url=d.source_url,
            sha256=sha,
        )
        chunks = chunk_sections(meta, sections)
        _apply_scan(meta, chunks, path, res)
        res.docs.append(meta)
        res.chunks += chunks
        res.naive += naive_chunks(meta, sections)


def run(dataroom: Path, corpus: Path, out: Path) -> IngestResult:
    out.mkdir(parents=True, exist_ok=True)
    cache = ParseCache(out / "parse_cache")
    res = IngestResult()
    ingest_dataroom(dataroom, cache, res)
    ingest_regulatory(corpus, cache, res)
    _write_jsonl(out / "chunks.jsonl", res.chunks)
    _write_jsonl(out / "naive_chunks.jsonl", res.naive)
    (out / "docs.json").write_text(
        json.dumps([d.model_dump(mode="json") for d in res.docs], indent=1)
    )
    (out / "quarantine.json").write_text(json.dumps(res.quarantine, indent=1))
    return res


def _write_jsonl(path: Path, chunks: list[Chunk]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(c.model_dump_json() + "\n")


def load_chunks(path: Path) -> list[Chunk]:
    return [Chunk.model_validate_json(line) for line in path.read_text().splitlines() if line]
