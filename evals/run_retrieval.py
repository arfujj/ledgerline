"""Retrieval eval over the seed (and, when present, approved golden) set, across ablation configs.

Writes evals/results/retrieval_<config>.json and evals/results/retrieval_summary.json.
Deterministic and free: local embeddings, no LLM calls.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from qdrant_client import QdrantClient

from evals.retrieval_metrics import Gold, mrr, ndcg_at_k, recall_at_k, relevance_vector
from ledgerline.core.settings import get_settings
from ledgerline.retrieval.store import ChunkStore

CONFIGS = {
    # name: (collection, mode, rerank)
    "naive_dense": ("ll_naive", "dense", False),
    "hybrid_nohdr": ("ll_hybrid_nohdr", "hybrid", False),
    "hybrid_nohdr_rerank": ("ll_hybrid_nohdr", "hybrid", True),
    "hybrid_hdr": ("ll_hybrid", "hybrid", False),
    "hybrid_hdr_rerank": ("ll_hybrid", "hybrid", True),
}
K = 10
HERE = Path(__file__).parent


def load_queries(paths: list[Path]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for p in paths:
        if p.exists():
            out += [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    return out


def evaluate(
    store: ChunkStore, queries: list[dict[str, object]], mode: str, rerank: bool
) -> dict[str, object]:
    rows = []
    for q in queries:
        gold = [Gold(**g) for g in q["gold"]]  # type: ignore[arg-type]
        t0 = time.perf_counter()
        hits = store.search(str(q["query"]), k=K, mode=mode, rerank=rerank)  # type: ignore[arg-type]
        ms = (time.perf_counter() - t0) * 1000
        rel = relevance_vector([(h.chunk.doc_id, h.chunk.text) for h in hits], gold)
        rows.append(
            {
                "qid": q["qid"],
                "type": q["type"],
                "recall@5": recall_at_k(rel, len(gold), 5),
                "recall@10": recall_at_k(rel, len(gold), 10),
                "mrr": mrr(rel),
                "ndcg@10": ndcg_at_k(rel, len(gold), 10),
                "latency_ms": ms,
                "top_doc": hits[0].chunk.doc_id if hits else None,
            }
        )

    def agg(key: str, subset: list[dict[str, object]]) -> float:
        return round(statistics.fmean(float(r[key]) for r in subset), 4) if subset else 0.0  # type: ignore[arg-type]

    lat = sorted(float(r["latency_ms"]) for r in rows)  # type: ignore[arg-type]
    by_type = {
        t: {
            m: agg(m, [r for r in rows if r["type"] == t])
            for m in ("recall@5", "recall@10", "mrr", "ndcg@10")
        }
        for t in sorted({str(r["type"]) for r in rows})
    }
    return {
        "n": len(rows),
        "overall": {m: agg(m, rows) for m in ("recall@5", "recall@10", "mrr", "ndcg@10")},
        "by_type": by_type,
        "latency_ms": {
            "p50": round(lat[len(lat) // 2], 1),
            "p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1),
        },
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="*", default=list(CONFIGS))
    ap.add_argument("--out", type=Path, default=HERE / "results")
    args = ap.parse_args()
    queries = load_queries(
        [HERE / "data" / "seed_retrieval.jsonl", HERE / "golden" / "approved.jsonl"]
    )
    client = QdrantClient(url=get_settings().qdrant_url)
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name in args.configs:
        coll, mode, rerank = CONFIGS[name]
        res = evaluate(ChunkStore(client, coll), queries, mode, rerank)
        (args.out / f"retrieval_{name}.json").write_text(json.dumps(res, indent=1))
        summary[name] = {"n": res["n"], **res["overall"], "latency_ms": res["latency_ms"]}  # type: ignore[dict-item]
        print(f"{name:22} n={res['n']} {res['overall']} lat={res['latency_ms']}")
    (args.out / "retrieval_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
