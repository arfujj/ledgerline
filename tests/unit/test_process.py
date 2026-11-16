from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from ledgerline.process.discovery import process_map
from ledgerline.process.metrics import MetricError, ProcessMetrics
from ledgerline.process.store import build

T0 = datetime(2026, 1, 5, 9)


def _ev(case: str, steps: list[tuple[str, float, str, bool]]) -> list[dict[str, object]]:
    return [
        {
            "case_id": case,
            "process": "x",
            "activity": a,
            "timestamp": T0 + timedelta(hours=h),
            "resource": r,
            "role": "SYSTEM" if r == "sys" else "ANALYST",
            "system": "s",
            "outcome": "ok",
            "is_manual": m,
        }
        for a, h, r, m in steps
    ]


@pytest.fixture
def pm(tmp_path: Path) -> ProcessMetrics:
    room = tmp_path / "room"
    (room / "event_logs").mkdir(parents=True)
    (room / "support").mkdir()
    kyc = _ev(
        "K1",
        [
            ("Start", 0, "sys", False),
            ("Review", 2, "ann", True),
            ("Review", 30, "bob", True),
            ("Done", 31, "sys", False),
        ],
    )
    kyc += _ev("K2", [("Start", 0, "sys", False), ("Done", 1, "sys", False)])
    pd.DataFrame(kyc).to_parquet(room / "event_logs" / "kyc_onboarding.parquet")
    for name in ("card_disputes", "daily_reconciliation"):
        pd.DataFrame(
            _ev("D1", [("Start", 0, "sys", False), ("Close", 24 * 50, "ann", True)])
        ).to_parquet(room / "event_logs" / f"{name}.parquet")
    pd.DataFrame(
        [
            {
                "ticket_id": "T1",
                "created_at": T0,
                "channel": "chat",
                "category": "a",
                "handled_by": "ai_agent",
                "handle_time_min": 6.0,
                "escalated_to_human": False,
                "csat": 4,
            }
        ]
    ).to_parquet(room / "support" / "support_tickets.parquet")
    db = build(room, tmp_path / "p.duckdb")
    return ProcessMetrics(db, tmp_path / "q")


def test_core_metrics(pm: ProcessMetrics) -> None:
    assert pm.run("case_count", "kyc").records() == [{"cases": 2}]
    ms = pm.run("manual_share", "kyc").records()[0]
    assert ms["manual_step_share"] == pytest.approx(2 / 6, abs=1e-3)
    rw = pm.run("rework_rate", "kyc").records()
    assert rw[0]["activity"] == "Review"
    assert rw[0]["rework_rate"] == 0.5
    assert pm.run("handoffs", "kyc").records()[0]["max_handoffs"] == 1
    b = pm.run("bottlenecks", "kyc", top_n=1).records()[0]
    assert b["activity"] == "Review"
    assert b["median_wait_h"] == pytest.approx(15.0)
    assert pm.run("sla_breach", "disputes").records()[0]["breach_rate"] == 1.0
    assert pm.run("activity_case_share", "kyc", activity="Review").records()[0]["share"] == 0.5
    assert pm.run("ticket_categories").records()[0]["ai_share"] == 1.0
    assert pm.run("variants", "kyc", top_n=5).records()[0]["cases"] == 1
    assert pm.run("late_step", "disputes", activity="Close").records()[0]["late_rate"] == 1.0
    assert len(pm.run("monthly_volume", "kyc").records()) == 1
    assert pm.run("resource_load", "kyc", activity="Review").records()[0]["share"] == 0.5
    assert "cycle_time" in pm.catalog()


def test_query_ids_are_stable_and_rerunnable(pm: ProcessMetrics) -> None:
    a = pm.run("cycle_time", "kyc")
    b = pm.run("cycle_time", "kyc")
    assert a.query_id == b.query_id
    assert a.cite() == f"[q:{a.query_id}]"
    res, same = pm.rerun(a.query_id)
    assert same
    assert res.rows == a.rows


def test_rejects_bad_inputs(pm: ProcessMetrics) -> None:
    with pytest.raises(MetricError, match="Unknown metric"):
        pm.run("DROP TABLE events", "kyc")
    with pytest.raises(MetricError, match="process must be"):
        pm.run("cycle_time", "kyc'; DROP TABLE events; --")
    with pytest.raises(MetricError, match="requires parameter"):
        pm.run("resource_load", "kyc")
    with pytest.raises(MetricError, match="Unexpected"):
        pm.run("cycle_time", "kyc", sql="x")
    # Injection through a bound parameter is inert.
    assert (
        pm.run("activity_case_share", "kyc", activity="x' OR '1'='1").records()[0][
            "cases_with_activity"
        ]
        == 0
    )


def test_connection_is_read_only(pm: ProcessMetrics) -> None:
    con = pm._connect()
    with pytest.raises(duckdb.Error):
        con.execute("DELETE FROM events")
    con.close()


def test_process_map(pm: ProcessMetrics) -> None:
    m = process_map(pm, "kyc")
    assert {e["source"] for e in m["edges"]} >= {"Start"}
    assert m["engine"] in ("sql-dfg", "pm4py-inductive")
    assert m["query_ids"]
