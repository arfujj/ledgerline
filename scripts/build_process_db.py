"""Build data/process.duckdb from the data room and print headline metrics."""

from __future__ import annotations

import sys

from ledgerline.core.settings import get_settings
from ledgerline.process.metrics import ProcessMetrics
from ledgerline.process.store import build


def main() -> int:
    s = get_settings()
    db = build(s.dataroom_dir, s.data_dir / "process.duckdb")
    pm = ProcessMetrics(db, s.data_dir / "queries")
    for proc in ("kyc", "disputes", "recon"):
        print(
            proc,
            pm.run("cycle_time", proc).records()[0],
            pm.run("manual_share", proc).records()[0],
            pm.run("handoffs", proc).records()[0],
        )
    print(
        "EDD load",
        pm.run("resource_load", "kyc", activity="Enhanced Due Diligence Review").records(),
    )
    print("bottlenecks kyc", pm.run("bottlenecks", "kyc", top_n=3).records())
    print(
        "late PC", pm.run("late_step", "disputes", activity="Provisional Credit Issued").records()
    )
    print("sla", pm.run("sla_breach", "disputes").records())
    return 0


if __name__ == "__main__":
    sys.exit(main())
