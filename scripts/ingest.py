"""Ingest data room + regulatory corpus and build Qdrant collections for retrieval and ablations.

Collections:
  ll_naive          fixed 1000-char chunks, dense only, no headers       (ablation baseline)
  ll_hybrid_nohdr   structure-aware chunks, dense+BM25, no headers        (ablation)
  ll_hybrid         structure-aware chunks, dense+BM25, contextual headers (default)
"""

from __future__ import annotations

import argparse
import sys
import time

from qdrant_client import QdrantClient

from ledgerline.core.settings import get_settings
from ledgerline.ingest import pipeline
from ledgerline.retrieval.store import ChunkStore


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdrant", default=None, help="Qdrant URL or ':memory:'")
    ap.add_argument("--skip-index", action="store_true")
    args = ap.parse_args()
    s = get_settings()
    t0 = time.time()
    res = pipeline.run(s.dataroom_dir, s.corpus_dir, s.data_dir / "ingest")
    print(
        f"parsed docs={len(res.docs)} chunks={len(res.chunks)} naive={len(res.naive)} "
        f"quarantined={[q['doc_id'] for q in res.quarantine]} ({time.time() - t0:.0f}s)"
    )
    if args.skip_index:
        return 0
    client = (
        QdrantClient(url=args.qdrant or s.qdrant_url)
        if (args.qdrant or s.qdrant_url) != ":memory:"
        else QdrantClient(":memory:")
    )
    for name, chunks, header, sparse in (
        ("ll_naive", res.naive, False, False),
        ("ll_hybrid_nohdr", res.chunks, False, True),
        ("ll_hybrid", res.chunks, True, True),
    ):
        t1 = time.time()
        store = ChunkStore(client, name)
        store.recreate(with_sparse=sparse)
        store.upsert(chunks, use_header=header, with_sparse=sparse)
        print(f"indexed {name}: {store.count()} points ({time.time() - t1:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
