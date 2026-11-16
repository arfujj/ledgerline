"""Fast, deterministic eval subset for CI (no API key, in-memory Qdrant, local embeddings).

Scope: data room + the *small* regulatory slice; seed queries whose gold docs are in scope.
Compares against evals/ci_baseline.json and exits 1 on a regression larger than TOLERANCE.

  uv run python -m evals.ci_subset              # check against baseline
  uv run python -m evals.ci_subset --update     # rewrite the baseline (commit it)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qdrant_client import QdrantClient

from evals.run_retrieval import evaluate, load_queries
from ledgerline.corpus.sources import select
from ledgerline.ingest.pipeline import load_chunks
from ledgerline.retrieval.store import ChunkStore

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "evals" / "ci_baseline.json"
TOLERANCE = 0.03
METRICS = ("recall@5", "recall@10", "mrr", "ndcg@10")


def run() -> dict[str, dict[str, float]]:
    small = {s.doc_id for s in select("small")}
    chunks = [
        c
        for c in load_chunks(ROOT / "data" / "ingest" / "chunks.jsonl")
        if c.corpus == "dataroom" or c.doc_id in small
    ]
    naive = [
        c
        for c in load_chunks(ROOT / "data" / "ingest" / "naive_chunks.jsonl")
        if c.corpus == "dataroom" or c.doc_id in small
    ]
    in_scope = {c.doc_id for c in chunks}
    queries = [
        q
        for q in load_queries([ROOT / "evals" / "data" / "seed_retrieval.jsonl"])
        if all(g["doc_id"] in in_scope for g in q["gold"])
    ]  # type: ignore[union-attr]
    client = QdrantClient(":memory:")
    out: dict[str, dict[str, float]] = {}
    for name, data, header, sparse, mode, rerank in (
        ("naive_dense", naive, False, False, "dense", False),
        ("hybrid_hdr_rerank", chunks, True, True, "hybrid", True),
    ):
        store = ChunkStore(client, name)
        store.recreate(with_sparse=sparse)
        store.upsert(data, use_header=header, with_sparse=sparse)
        res = evaluate(store, queries, mode, rerank)
        out[name] = {"n": res["n"], **res["overall"]}  # type: ignore[dict-item]
        print(name, out[name])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()
    current = run()
    if args.update or not BASELINE.exists():
        BASELINE.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n")
        print(f"baseline written to {BASELINE}")
        return 0
    base = json.loads(BASELINE.read_text())
    failures = [
        f"{cfg}.{m}: {current[cfg][m]:.3f} < baseline {base[cfg][m]:.3f} - {TOLERANCE}"
        for cfg in base
        for m in METRICS
        if cfg in current and current[cfg][m] < base[cfg][m] - TOLERANCE
    ]
    for f in failures:
        print("REGRESSION", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
