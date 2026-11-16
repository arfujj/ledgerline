"""Fetch the public regulatory/standards corpus (idempotent, cached, failures logged).

Usage: uv run python scripts/fetch_regulatory_corpus.py [--slice small|full] [--refresh]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ledgerline.corpus.fetch import Fetcher
from ledgerline.corpus.sources import select


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", choices=["small", "full"], default="small")
    ap.add_argument("--out", type=Path, default=Path("corpus/regulatory"))
    ap.add_argument("--refresh", action="store_true", help="revalidate cached files (ETag)")
    args = ap.parse_args()
    sources = select(args.slice)
    f = Fetcher(args.out)
    manifest = f.run(sources, refresh=args.refresh)
    ok = {d.doc_id for d in manifest.docs}
    failed = [s.doc_id for s in sources if s.doc_id not in ok]
    for d in manifest.docs:
        print(
            f"{d.doc_id:18} {d.doc_type:14} pub={d.publication_date} eff={d.effective_date} "
            f"valid_to={d.valid_to} {d.title[:60]}"
        )
    print(f"fetched={len(ok)} failed={len(failed)} network_calls={f.network_calls} {failed or ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
