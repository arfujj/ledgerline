"""Temporal correctness: for as-of questions, does retrieval surface the version that governed?

Compares plain hybrid retrieval vs. version-aware retrieval (as_of payload filter).
Questions: template-built temporal items in evals/golden/{approved,candidates}.jsonl.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from qdrant_client import QdrantClient

from ledgerline.core.settings import get_settings
from ledgerline.corpus.manifest import Manifest
from ledgerline.retrieval.store import ChunkStore
from ledgerline.retrieval.temporal import version_as_of

ROOT = Path(__file__).resolve().parents[1]


def load() -> list[dict[str, object]]:
    for name in ("approved.jsonl", "candidates.jsonl"):
        p = ROOT / "evals" / "golden" / name
        if p.exists():
            items = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
            t = [
                i
                for i in items
                if i["type"] == "temporal" and i.get("as_of") and i.get("source") == "template"
            ]
            if t:
                return t
    return []


def main() -> int:
    manifest = Manifest.load(ROOT / "corpus" / "regulatory" / "manifest.json")
    lineage_of = {d.doc_id: d.lineage_id for d in manifest.docs}
    store = ChunkStore(QdrantClient(url=get_settings().qdrant_url), "ll_hybrid")
    qs = load()
    res: dict[str, dict[str, float]] = {}
    rows = []
    for mode in ("no_filter", "as_of_filter"):
        correct = 0
        for q in qs:
            gold = q["gold"][0]["doc_id"]  # type: ignore[index]
            lineage = lineage_of[gold]
            as_of = date.fromisoformat(str(q["as_of"]))
            hits = store.search(
                str(q["question"]),
                k=20,
                corpus="regulatory",
                doc_ids=[d for d, ln in lineage_of.items() if ln == lineage],
                as_of=as_of if mode == "as_of_filter" else None,
            )
            top = hits[0].chunk.doc_id if hits else None
            status_ok = version_as_of(manifest, lineage, as_of).doc_id == gold
            ok = top == gold and status_ok
            correct += ok
            rows.append(
                {
                    "mode": mode,
                    "qid": q["qid"],
                    "as_of": q["as_of"],
                    "gold": gold,
                    "top": top,
                    "correct": ok,
                }
            )
        res[mode] = {
            "n": len(qs),
            "temporal_correctness": round(correct / len(qs), 4) if qs else 0.0,
        }
        print(mode, res[mode])
    out = ROOT / "evals" / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "temporal.json").write_text(json.dumps({"summary": res, "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
