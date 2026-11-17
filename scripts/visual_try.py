"""Try visual retrieval + page reading on one question."""

from __future__ import annotations

import sys

from ledgerline.agents.context import AppContext
from ledgerline.retrieval.visual import search_pages, visual_search


def main() -> int:
    q = (
        " ".join(sys.argv[1:])
        or "What share of disputes filed in August were resolved after 45 days?"
    )
    ctx = AppContext()
    pages, mode = search_pages(ctx, q, 3)
    print(mode, [p.page_id for p in pages])
    for e in visual_search(ctx, q, 2):
        print(e.cites, e.text[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
