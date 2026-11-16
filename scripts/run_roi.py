"""Print the base-case opportunity ranking, scenario NPVs and top sensitivities."""

from __future__ import annotations

import sys
from pathlib import Path

from ledgerline.core.settings import get_settings
from ledgerline.process.metrics import ProcessMetrics
from ledgerline.roi.model import ROIModel, load_assumptions, load_catalogue


def main() -> int:
    s = get_settings()
    pm = ProcessMetrics(s.data_dir / "process.duckdb", s.data_dir / "queries")
    m = ROIModel(
        load_assumptions(Path("config/roi_assumptions.yaml")),
        load_catalogue(Path("config/opportunities.yaml")),
        pm,
    )
    print(f"data window: {m.data_months} months")
    for r in m.evaluate_all():
        print(
            f"{r.id:18} {r.priority:14} hours={r.annual_hours_saved:>8,.0f} "
            f"value=${r.annual_value_usd:>9,.0f} impl=${r.implementation_cost_usd:>8,.0f} "
            f"NPV=${r.npv_usd:>10,.0f} payback={r.payback_months} mo  "
            f"V={r.value_score} E={r.effort_score}"
        )
    sc = m.scenarios()
    for name, res in sc.items():
        print(name, {r.id: r.npv_usd for r in res})
    top = m.sensitivity(m.catalogue[0])[:3]
    print("tornado", m.catalogue[0]["id"], [(t.assumption_id, t.npv_low, t.npv_high) for t in top])
    return 0


if __name__ == "__main__":
    sys.exit(main())
