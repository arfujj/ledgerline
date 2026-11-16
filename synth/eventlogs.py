"""Event-log simulators for KYC onboarding, card disputes, and daily reconciliation.

Deliberate, documented problems are baked in: rework loops, manual handoffs, SLA breaches,
a two-person EDD bottleneck, and a ~40% manual reconciliation process.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from synth.world import World

COLUMNS = [
    "case_id",
    "process",
    "activity",
    "timestamp",
    "resource",
    "role",
    "system",
    "outcome",
    "is_manual",
]


@dataclass
class _Rows:
    rows: list[tuple[object, ...]]

    def add(
        self,
        case: str,
        process: str,
        activity: str,
        ts: datetime,
        resource: str,
        role: str,
        system: str,
        outcome: str,
        manual: bool,
    ) -> None:
        self.rows.append((case, process, activity, ts, resource, role, system, outcome, manual))


def _start_time(rng: np.random.Generator, w: World) -> datetime:
    days = (w.period_end - w.period_start).days
    d = w.period_start + timedelta(days=int(rng.integers(0, days)))
    while d.weekday() >= 5 and rng.random() < 0.7:  # weekday-heavy arrivals
        d += timedelta(days=1)
    hour = float(np.clip(rng.normal(13, 3.5), 0, 23.9))
    return datetime(d.year, d.month, d.day) + timedelta(hours=hour)


def _hours(rng: np.random.Generator, median: float, sigma: float = 0.6) -> timedelta:
    return timedelta(hours=float(rng.lognormal(np.log(median), sigma)))


def simulate_kyc(w: World, rng: np.random.Generator) -> pd.DataFrame:
    out = _Rows([])
    analysts = [p.name for p in w.people_by_role("KYC_ANALYST")]
    analyst_p = np.array([0.31, 0.27, 0.24, 0.18])
    edd = [p.name for p in w.people_by_role("COMPLIANCE_ANALYST")]
    p_rework_given_manual = 0.55
    p_idv_fail = w.kyc_rework_rate_target / p_rework_given_manual
    for i in range(w.kyc_cases):
        cid = f"KYC-{i:06d}"
        t = _start_time(rng, w)
        out.add(
            cid,
            "kyc",
            "Application Submitted",
            t,
            "customer",
            "CUSTOMER",
            "NovaPay App",
            "submitted",
            False,
        )
        t += _hours(rng, 0.5, 1.2)
        out.add(
            cid,
            "kyc",
            "Documents Uploaded",
            t,
            "customer",
            "CUSTOMER",
            "NovaPay App",
            "uploaded",
            False,
        )
        t += timedelta(minutes=float(rng.uniform(1, 6)))
        idv_fail = rng.random() < p_idv_fail
        out.add(
            cid,
            "kyc",
            "Automated ID Verification",
            t,
            "VerifID API",
            "SYSTEM",
            "VerifID",
            "fail" if idv_fail else "pass",
            False,
        )
        manual_path = idv_fail
        if idv_fail:
            loops = 0
            while True:
                t += _hours(rng, 5.0)
                analyst = str(rng.choice(analysts, p=analyst_p))
                needs_info = loops < 2 and rng.random() < (
                    p_rework_given_manual if loops == 0 else 0.25
                )
                out.add(
                    cid,
                    "kyc",
                    "Manual Document Review",
                    t,
                    analyst,
                    "KYC_ANALYST",
                    "LedgerCore Console",
                    "needs_info" if needs_info else "pass",
                    True,
                )
                if not needs_info:
                    break
                t += _hours(rng, 0.7)
                out.add(
                    cid,
                    "kyc",
                    "Request Additional Information",
                    t,
                    analyst,
                    "KYC_ANALYST",
                    "Email",
                    "sent",
                    True,
                )
                t += _hours(rng, 26.0, 0.8)
                out.add(
                    cid,
                    "kyc",
                    "Documents Uploaded",
                    t,
                    "customer",
                    "CUSTOMER",
                    "NovaPay App",
                    "uploaded",
                    False,
                )
                loops += 1
        t += timedelta(minutes=float(rng.uniform(1, 10)))
        hit = rng.random() < w.kyc_edd_rate
        out.add(
            cid,
            "kyc",
            "Sanctions & PEP Screening",
            t,
            "ScreenSafe",
            "SYSTEM",
            "ScreenSafe",
            "potential_match" if hit else "clear",
            False,
        )
        if hit:
            # Two-person bottleneck: long queue wait before EDD review.
            t += _hours(rng, 31.0, 0.7)
            reviewer = str(rng.choice(edd, p=[0.63, 0.37]))
            out.add(
                cid,
                "kyc",
                "Enhanced Due Diligence Review",
                t,
                reviewer,
                "COMPLIANCE_ANALYST",
                "Spreadsheet + LedgerCore",
                "cleared",
                True,
            )
            manual_path = True
        t += timedelta(minutes=float(rng.uniform(1, 5)))
        out.add(
            cid,
            "kyc",
            "Risk Rating Assigned",
            t,
            "Risk Engine",
            "SYSTEM",
            "LedgerCore",
            "assigned",
            False,
        )
        rejected = rng.random() < (0.12 if hit else 0.04)
        if manual_path:
            t += _hours(rng, 3.0)
            out.add(
                cid,
                "kyc",
                "Approval Decision",
                t,
                str(rng.choice(analysts, p=analyst_p)),
                "KYC_ANALYST",
                "LedgerCore Console",
                "rejected" if rejected else "approved",
                True,
            )
        else:
            t += timedelta(minutes=float(rng.uniform(0.5, 3)))
            out.add(
                cid,
                "kyc",
                "Approval Decision",
                t,
                "Risk Engine",
                "SYSTEM",
                "LedgerCore",
                "rejected" if rejected else "approved",
                False,
            )
        if not rejected:
            t += timedelta(minutes=float(rng.uniform(1, 30)))
            out.add(
                cid,
                "kyc",
                "Account Activated",
                t,
                "LedgerCore",
                "SYSTEM",
                "LedgerCore",
                "active",
                False,
            )
    return pd.DataFrame(out.rows, columns=COLUMNS)


def _add_business_days(start: datetime, n: float) -> datetime:
    whole = int(n)
    d = start
    added = 0
    while added < whole:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d + timedelta(days=n - whole)


def simulate_disputes(w: World, rng: np.random.Generator) -> pd.DataFrame:
    out = _Rows([])
    specialists = [p.name for p in w.people_by_role("DISPUTES_SPECIALIST")]
    lead = w.people_by_role("DISPUTES_LEAD")[0].name
    ai_start = datetime(2026, 6, 1)
    for i in range(w.dispute_cases):
        cid = f"DSP-{i:06d}"
        t0 = _start_time(rng, w)
        breach = rng.random() < w.dispute_sla_breach_target
        total_days = (
            float(rng.uniform(46, 95))
            if breach
            else float(np.clip(rng.lognormal(np.log(19), 0.45), 4, 44.5))
        )
        end = t0 + timedelta(days=total_days)
        out.add(
            cid,
            "disputes",
            "Dispute Filed",
            t0,
            "customer",
            "CUSTOMER",
            str(rng.choice(["NovaPay App", "Phone"], p=[0.7, 0.3])),
            "filed",
            False,
        )
        owner = str(rng.choice(specialists))
        t = t0 + _hours(rng, 6.0)
        if t0 >= ai_start and rng.random() < 0.4:
            out.add(
                cid,
                "disputes",
                "Intake Triage",
                t,
                "Parley Assist",
                "AI_AGENT",
                "Parley AI",
                "triaged",
                False,
            )
        else:
            out.add(
                cid,
                "disputes",
                "Intake Triage",
                t,
                owner,
                "DISPUTES_SPECIALIST",
                "LedgerCore Console",
                "triaged",
                True,
            )
        late = rng.random() < w.dispute_late_provisional_credit_target
        bd = float(rng.uniform(10.5, 22)) if late else float(rng.uniform(1, 9.5))
        pc = _add_business_days(t0, bd)
        steps: list[tuple[str, str, str, str, bool]] = [
            ("Provisional Credit Issued", owner, "DISPUTES_SPECIALIST", "credited", True),
            ("Merchant Evidence Requested", owner, "DISPUTES_SPECIALIST", "requested", True),
        ]
        inv = owner if rng.random() < 0.45 else str(rng.choice(specialists))
        steps.append(("Investigation", inv, "DISPUTES_SPECIALIST", "in_progress", True))
        if rng.random() < 0.27:
            steps.append(("Additional Info Requested", inv, "DISPUTES_SPECIALIST", "sent", True))
            steps.append(("Customer Info Received", "customer", "CUSTOMER", "received", False))
            steps.append(
                (
                    "Investigation",
                    str(rng.choice(specialists)),
                    "DISPUTES_SPECIALIST",
                    "in_progress",
                    True,
                )
            )
        steps.append(("Chargeback Submitted", "Cardinal Network", "SYSTEM", "submitted", False))
        if rng.random() < 0.35:
            steps.append(
                ("Representment Received", "Cardinal Network", "SYSTEM", "received", False)
            )
            steps.append(("Second Review", lead, "DISPUTES_LEAD", "reviewed", True))
        decision = str(
            rng.choice(["customer_won", "merchant_won", "partial"], p=[0.62, 0.28, 0.10])
        )
        steps.append(
            ("Decision", lead if rng.random() < 0.3 else inv, "DISPUTES_SPECIALIST", decision, True)
        )
        steps.append(("Customer Notified", inv, "DISPUTES_SPECIALIST", "notified", True))
        n = len(steps)
        # Provisional credit at its own (possibly late) time; remaining steps spread to `end`.
        pc_ts = min(pc, t0 + timedelta(days=total_days * 0.5))
        if late:
            pc_ts = pc
        fracs = np.sort(rng.uniform(0.0, 1.0, n - 2))
        out.add(
            cid,
            "disputes",
            steps[0][0],
            pc_ts,
            steps[0][1],
            steps[0][2],
            "LedgerCore Console",
            steps[0][3],
            steps[0][4],
        )
        span_start = max(pc_ts, t + timedelta(hours=1))
        span = end - span_start
        for (act, res, role, outc, man), f in zip(steps[1:-1], fracs, strict=True):
            sys = (
                "Cardinal"
                if res == "Cardinal Network"
                else ("NovaPay App" if res == "customer" else "LedgerCore Console")
            )
            out.add(cid, "disputes", act, span_start + span * float(f), res, role, sys, outc, man)
        last = steps[-1]
        out.add(
            cid,
            "disputes",
            last[0],
            end - timedelta(hours=2),
            last[1],
            last[2],
            "Email",
            last[3],
            last[4],
        )
        out.add(
            cid,
            "disputes",
            "Case Closed",
            end,
            "LedgerCore",
            "SYSTEM",
            "LedgerCore",
            "closed",
            False,
        )
    return pd.DataFrame(out.rows, columns=COLUMNS)


def simulate_recon(w: World, rng: np.random.Generator) -> pd.DataFrame:
    out = _Rows([])
    analysts = [p.name for p in w.people_by_role("RECON_ANALYST")]
    approver = w.people_by_role("FINOPS_LEAD")[0].name
    d = w.period_start
    while d <= w.period_end:
        if d.weekday() < 5:
            for rail in w.recon_rails:
                cid = f"REC-{d:%Y%m%d}-{rail}"
                t = datetime(d.year, d.month, d.day, 6, 0) + timedelta(
                    minutes=float(rng.uniform(0, 20))
                )
                a = str(rng.choice(analysts))

                def auto(act: str, system: str, outcome: str = "ok", _cid: str = cid) -> None:
                    nonlocal t
                    t += timedelta(minutes=float(rng.uniform(2, 15)))
                    out.add(_cid, "recon", act, t, system, "SYSTEM", system, outcome, False)

                def manual(
                    act: str,
                    who: str,
                    system: str,
                    outcome: str = "done",
                    median_h: float = 0.8,
                    _cid: str = cid,
                ) -> None:
                    nonlocal t
                    t += _hours(rng, median_h, 0.5)
                    out.add(
                        _cid,
                        "recon",
                        act,
                        t,
                        who,
                        "RECON_ANALYST" if who != approver else "FINOPS_LEAD",
                        system,
                        outcome,
                        True,
                    )

                auto("Bank Statement Import", "LedgerCore")
                auto("Ledger Extract", "LedgerCore")
                auto("Auto-Match", "ReconWorks", "partial")
                auto("Balance Check", "ReconWorks")
                manual("Exception Export to Spreadsheet", a, "Excel", median_h=0.6)
                manual("Manual Matching", a, "Excel", median_h=1.6)
                if rng.random() < 0.5:
                    manual("Break Investigation", a, "Excel + Email", "investigated", 2.2)
                    if rng.random() < 0.15:
                        manual(
                            "Break Investigation",
                            str(rng.choice(analysts)),
                            "Excel + Email",
                            "escalated",
                            3.0,
                        )
                if rng.random() < 0.33:
                    manual("Journal Adjustment Prepared", a, "LedgerCore Console", median_h=0.7)
                    manual(
                        "Adjustment Approval",
                        approver,
                        "LedgerCore Console",
                        "approved",
                        median_h=2.5,
                    )
                auto("Variance Calculation", "ReconWorks")
                manual("Recon Sign-off", a, "Excel", "signed", 0.4)
                auto("Recon Report Published", "LedgerCore", "published")
        d += timedelta(days=1)
    return pd.DataFrame(out.rows, columns=COLUMNS)


def simulate_tickets(w: World, rng: np.random.Generator) -> pd.DataFrame:
    cats = {
        # category: (weight, median handle minutes, ai_eligible)
        "card_dispute_status": (0.24, 14.0, True),
        "kyc_verification_status": (0.17, 11.0, True),
        "transfer_delay": (0.15, 16.0, True),
        "login_access": (0.12, 7.0, True),
        "fees_question": (0.10, 6.0, True),
        "card_lost_stolen": (0.08, 9.0, False),
        "fraud_report": (0.07, 24.0, False),
        "stablecoin_waitlist": (0.04, 5.0, True),
        "complaint_escalation": (0.03, 38.0, False),
    }
    names = list(cats)
    weights = np.array([cats[c][0] for c in names])
    rows = []
    ai_start = datetime(2026, 6, 1)
    for i in range(w.tickets):
        c = str(rng.choice(names, p=weights / weights.sum()))
        created = _start_time(rng, w)
        ai = created >= ai_start and cats[c][2] and rng.random() < 0.45
        handle = float(rng.lognormal(np.log(cats[c][1] * (0.35 if ai else 1.0)), 0.5))
        escalated = bool(rng.random() < (0.22 if ai else 0.08))
        rows.append(
            {
                "ticket_id": f"TCK-{i:05d}",
                "created_at": created,
                "channel": str(rng.choice(["chat", "email", "phone"], p=[0.5, 0.3, 0.2])),
                "category": c,
                "handled_by": "ai_agent" if ai else "human",
                "handle_time_min": round(handle, 1),
                "escalated_to_human": escalated if ai else False,
                "csat": int(np.clip(round(rng.normal(3.6 if ai else 4.1, 0.9)), 1, 5)),
            }
        )
    return pd.DataFrame(rows)
