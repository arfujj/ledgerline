"""Queue findings for review (if not already) and export deliverables for a run."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ledgerline.core.settings import get_settings
from ledgerline.deliverables.build import build_all, export, pdf_page_count
from ledgerline.review.queue import ReviewQueue


def main() -> int:
    s = get_settings()
    root = s.data_dir / "engagement"
    run_id = sys.argv[1] if len(sys.argv) > 1 else (root / "LATEST").read_text().strip()
    eng = json.loads((root / run_id / "engagement.json").read_text())
    q = ReviewQueue(s.postgres_dsn)
    findings = eng["gaps"] + eng["inefficiencies"] + eng["security"]
    print("queued", q.enqueue(run_id, findings))
    reviewed = q.reviewed_findings(run_id)
    paths = export(
        build_all(eng, reviewed, s.data_dir, Path("config"), q.summary(run_id)),
        root / run_id / "deliverables",
    )
    for name, p in paths.items():
        print(name, p["pdf"], f"{pdf_page_count(Path(p['pdf']))} pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
