"""Ground-truth metrics measured from the simulated logs (feed board decks and the answer key)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]


def _case_spans(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("case_id").timestamp
    return pd.DataFrame({"start": g.min(), "end": g.max()})


def _business_days(start: pd.Series, end: pd.Series) -> np.ndarray:
    return np.busday_count(start.values.astype("datetime64[D]"), end.values.astype("datetime64[D]"))


def compute(
    kyc: pd.DataFrame,
    disputes: pd.DataFrame,
    recon: pd.DataFrame,
    tickets: pd.DataFrame,
    extract: pd.Timestamp | None = None,
) -> dict[str, Any]:
    m: dict[str, Any] = {"months": MONTHS}
    # KYC
    ks = _case_spans(kyc)
    ks["month"] = ks.start.dt.month
    ks["quarter"] = ks.start.dt.quarter
    decided = kyc[kyc.activity == "Approval Decision"].groupby("case_id").timestamp.max()
    ks["decision_h"] = (decided - ks.start).dt.total_seconds() / 3600
    m["kyc_by_month"] = [int((ks.month == i).sum()) for i in range(1, 10)]
    m["kyc_cases"] = len(ks)
    rework_cases = kyc[kyc.activity == "Request Additional Information"].case_id.unique()
    m["kyc_rework_rate"] = round(len(rework_cases) / len(ks), 4)
    screen = kyc[kyc.activity == "Sanctions & PEP Screening"].set_index("case_id").timestamp
    edd = kyc[kyc.activity == "Enhanced Due Diligence Review"].set_index("case_id")
    edd_wait = (edd.timestamp - screen.reindex(edd.index)).dt.total_seconds() / 3600
    m["kyc_edd_cases"] = len(edd)
    m["kyc_edd_rate"] = round(len(edd) / len(ks), 4)
    m["kyc_edd_median_wait_h"] = round(float(edd_wait.median()), 1)
    m["kyc_edd_p90_wait_h"] = round(float(edd_wait.quantile(0.9)), 1)
    m["kyc_edd_reviewers"] = sorted(edd.resource.unique().tolist())
    m["kyc_edd_top_reviewer_share"] = round(
        float(edd.resource.value_counts(normalize=True).iloc[0]), 4
    )
    m["kyc_within_48h"] = {
        q: round(float((ks[ks.quarter == q].decision_h <= 48).mean()), 4) for q in (1, 2, 3)
    }
    # Disputes
    ds = _case_spans(disputes)
    closed = disputes[disputes.activity == "Case Closed"].groupby("case_id").timestamp.max()
    m["dispute_open_at_extract"] = int(len(ds) - len(closed))
    if extract is not None:
        # Open cases are aged to the extract date (right-censored).
        ds["end"] = closed.reindex(ds.index).fillna(extract)
    ds["days"] = (ds.end - ds.start).dt.total_seconds() / 86400
    ds["month"] = ds.start.dt.month
    ds["quarter"] = ds.start.dt.quarter
    pc = disputes[disputes.activity == "Provisional Credit Issued"].set_index("case_id").timestamp
    pc_ts = pc.reindex(ds.index).fillna(extract if extract is not None else ds.end)
    ds["pc_bd"] = _business_days(ds.start, pc_ts)
    m["dispute_cases"] = len(ds)
    m["dispute_sla_breach_rate"] = round(float((ds.days > 45).mean()), 4)
    m["dispute_late_pc_rate"] = round(float((ds.pc_bd > 10).mean()), 4)
    m["dispute_median_days"] = round(float(ds.days.median()), 1)
    m["disputes_by_month"] = [int((ds.month == i).sum()) for i in range(1, 10)]
    m["dispute_breach_pct_by_month"] = [
        round(float((ds[ds.month == i].days > 45).mean() * 100), 1) for i in range(1, 10)
    ]
    hand = disputes[disputes.role.isin(["DISPUTES_SPECIALIST", "DISPUTES_LEAD"])]
    handoffs = (
        hand.sort_values("timestamp")
        .groupby("case_id")
        .resource.apply(lambda s: int((s != s.shift()).sum() - 1))
    )
    m["dispute_avg_handoffs"] = round(float(handoffs.mean()), 2)
    m["dispute_rework_rate"] = round(
        float(
            disputes[disputes.activity == "Additional Info Requested"].case_id.nunique() / len(ds)
        ),
        4,
    )
    # Recon
    m["recon_cases"] = int(recon.case_id.nunique())
    m["recon_events"] = len(recon)
    m["recon_manual_share"] = round(float(recon.is_manual.mean()), 4)
    r = recon.sort_values(["case_id", "timestamp"]).copy()
    r["dur_h"] = r.groupby("case_id").timestamp.diff().dt.total_seconds() / 3600
    manual = r[r.is_manual]
    m["recon_manual_hours_total"] = round(float(manual.dur_h.sum()), 1)
    m["recon_manual_hours_by_month"] = [
        round(float(manual[manual.timestamp.dt.month == i].dur_h.sum()), 1) for i in range(1, 10)
    ]
    signoff = r[r.activity == "Recon Sign-off"]
    m["recon_signoff_on_time"] = round(
        float((signoff.timestamp.dt.hour + signoff.timestamp.dt.minute / 60 <= 11).mean()), 4
    )
    m["recon_manual_time_share"] = round(float(manual.dur_h.sum() / r.dur_h.sum()), 4)
    # Tickets
    t = tickets
    m["tickets"] = len(t)
    m["ticket_category_share"] = t.category.value_counts(normalize=True).round(4).to_dict()
    pilot = t[t.created_at >= pd.Timestamp("2026-06-01")]
    rows = []
    for label, fn in [
        ("Tickets", lambda d: f"{len(d):,}"),
        ("Median handle time (min)", lambda d: f"{d.handle_time_min.median():.1f}"),
        ("Escalated to human", lambda d: f"{d.escalated_to_human.mean() * 100:.0f}%"),
        ("Average CSAT (1-5)", lambda d: f"{d.csat.mean():.2f}"),
    ]:
        rows.append(
            [
                label,
                fn(pilot[pilot.handled_by == "human"]),
                fn(pilot[pilot.handled_by == "ai_agent"]),
            ]
        )
    m["ai_pilot_rows"] = rows
    m["ai_pilot_csat"] = {
        k: round(float(v), 2) for k, v in pilot.groupby("handled_by").csat.mean().items()
    }

    def q(series_fn: Any) -> list[str]:
        return [series_fn(i) for i in (1, 2, 3)]

    so_hour = signoff.timestamp.dt.hour
    so_q = signoff.timestamp.dt.quarter

    def row(label: str, fn: Any, target: str) -> list[str]:
        return [label, *q(fn), target]

    m["kpi_rows"] = [
        row("KYC applications", lambda i: f"{int((ks.quarter == i).sum()):,}", "-"),
        row("KYC decided within 2 days", lambda i: f"{m['kyc_within_48h'][i] * 100:.0f}%", "90%"),
        row("Disputes filed", lambda i: f"{int((ds.quarter == i).sum()):,}", "-"),
        row(
            "Disputes resolved > 45 days",
            lambda i: f"{(ds[ds.quarter == i].days > 45).mean() * 100:.1f}%",
            "0%",
        ),
        row(
            "Recon sign-off by 11:00",
            lambda i: f"{(so_hour[so_q == i] < 11).mean() * 100:.0f}%",
            "100%",
        ),
    ]
    return m
