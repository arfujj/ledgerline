from __future__ import annotations

from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from ledgerline.process.metrics import QueryResult
from ledgerline.roi.model import ROIModel, classify, load_assumptions, load_catalogue

ROOT = Path(__file__).resolve().parents[2]
A = load_assumptions(ROOT / "config" / "roi_assumptions.yaml")
CAT = load_catalogue(ROOT / "config" / "opportunities.yaml")


class FakePM:
    def __init__(self, scale: float = 1.0) -> None:
        self.scale = scale

    def run(self, metric: str, process: str | None = None, **_: Any) -> QueryResult:
        if metric == "ticket_categories":
            rows = [["card_dispute_status", 900.0 * self.scale], ["fees_question", 50.0]]
            cols = ["category", "total_handle_hours"]
        elif metric == "monthly_volume":
            rows, cols = [[f"2026-0{i}", 1] for i in range(1, 10)], ["month", "cases"]
        else:
            acts = [o for o in CAT if o.get("volume", {}).get("process") == process]
            names = [a for o in acts for a in o["volume"]["activities"]]
            rows = [[n, 1000.0 * self.scale, 400.0 * self.scale] for n in names]
            cols = ["activity", "events", "total_elapsed_h"]
        return QueryResult(f"q_{metric}_{process}", metric, {}, "sql", cols, rows, "h")


def _model(scale: float = 1.0) -> ROIModel:
    return ROIModel(A, CAT, FakePM(scale))  # type: ignore[arg-type]


def test_every_number_is_cited() -> None:
    m = _model()
    for r in m.evaluate_all():
        assert r.citations
        assert all(c.startswith(("[q:", "[a:")) for c in r.citations)
        assert any(c.startswith("[q:") for c in r.citations)
        assert r.priority in {"quick_win", "strategic_bet", "fill_in", "deprioritize"}
    assert m.data_months == 9.0


def test_scenarios_are_ordered() -> None:
    sc = _model().scenarios()
    for o in CAT:
        lo = next(r for r in sc["low"] if r.id == o["id"]).npv_usd
        base = next(r for r in sc["base"] if r.id == o["id"]).npv_usd
        hi = next(r for r in sc["high"] if r.id == o["id"]).npv_usd
        assert lo <= base <= hi


def test_sensitivity_sorted_by_swing() -> None:
    sens = _model().sensitivity(CAT[0])
    assert sens
    assert [s.swing for s in sens] == sorted((s.swing for s in sens), reverse=True)


@settings(max_examples=30, deadline=None)
@given(st.floats(min_value=0.1, max_value=5.0), st.floats(min_value=1.01, max_value=3.0))
def test_more_volume_never_reduces_value(scale: float, bump: float) -> None:
    for o in CAT:
        a = _model(scale).evaluate(o)
        b = _model(scale * bump).evaluate(o)
        assert b.annual_value_usd >= a.annual_value_usd
        assert b.npv_usd >= a.npv_usd


def test_higher_cost_never_increases_npv() -> None:
    m = _model()
    for o in CAT:
        lo = m.evaluate(o, "base", {o["impl_cost"]: "low"}).npv_usd
        hi = m.evaluate(o, "base", {o["impl_cost"]: "high"}).npv_usd
        assert hi <= lo


def test_classify_rules() -> None:
    m = _model()
    base = m.evaluate(CAT[0])
    neg = base.model_copy(update={"npv_usd": -1.0})
    qw = base.model_copy(
        update={"npv_usd": 10.0, "time_to_value_months": 2, "implementation_cost_usd": 50_000}
    )
    sb = base.model_copy(update={"npv_usd": 500_000, "time_to_value_months": 6})
    fi = base.model_copy(update={"npv_usd": 50_000, "time_to_value_months": 6})
    got = {r.npv_usd: r.priority for r in classify([neg, qw, sb, fi])}
    assert got == {
        -1.0: "deprioritize",
        10.0: "quick_win",
        500_000: "strategic_bet",
        50_000: "fill_in",
    }
    assert classify([]) == []
