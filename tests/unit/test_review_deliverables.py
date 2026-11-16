from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ledgerline.deliverables.build import build_all, export, pdf_page_count, to_markdown
from ledgerline.deliverables.citations import CitationResolver
from ledgerline.review.queue import ReviewError, ReviewQueue

ROOT = Path(__file__).resolve().parents[2]

F1: dict[str, Any] = {
    "finding_id": "F-GAP-01",
    "category": "compliance_gap",
    "title": "Reserves rehypothecated",
    "severity": "critical",
    "status": "partial",
    "evidence_citations": ["[doc:CTR-V#p1]"],
    "requirement_citations": ["[doc:LAW#s4(a)(2)]"],
    "rationale": "Custodian may pledge.",
    "recommendation": "Amend custody agreement.",
    "owner": "Treasury",
    "confidence": 0.8,
}
F2: dict[str, Any] = {
    **F1,
    "finding_id": "F-INEF-01",
    "category": "inefficiency",
    "title": "Recon 41.6% manual",
    "severity": "high",
    "evidence_citations": ["[q:q_abc]"],
    "requirement_citations": [],
}


def _engagement() -> dict[str, Any]:
    sent = {
        "text": "Reconciliation is 41.6% manual.",
        "cites": ["[q:q_abc]", "[a:discount_rate]"],
        "evidence_ids": ["E1"],
        "status": "supported",
        "note": "",
    }
    opp = {
        "id": "OPP-1",
        "title": "Automate matching",
        "priority": "strategic_bet",
        "annual_hours_saved": 2322.0,
        "annual_value_usd": 157865.0,
        "implementation_cost_usd": 140000.0,
        "npv_usd": 135118.0,
        "payback_months": 16.9,
        "citations": ["[q:q_abc]", "[a:discount_rate]"],
    }
    return {
        "run_id": "r1",
        "model": "claude-haiku-5-5",
        "memo": [{"title": "Executive summary", "sentences": [sent]}],
        "roadmap": [
            {
                "window": "Days 0-30",
                "type": "remediation",
                "ref": "F-GAP-01",
                "action": "Amend custody agreement",
                "owner": "Treasury",
                "track": "quick_win",
                "citations": ["[doc:CTR-V#p1]"],
            },
            {
                "window": "Days 31-90",
                "type": "opportunity",
                "ref": "OPP-1",
                "action": "Automate matching",
                "owner": "COO",
                "track": "strategic_bet",
                "citations": ["[q:q_abc]"],
                "value": "x",
            },
        ],
        "opportunities": [opp],
        "scenarios": {"low": [{**opp, "npv_usd": -1.0}], "high": [{**opp, "npv_usd": 9.0}]},
        "sensitivity": {
            "OPP-1": [{"assumption_id": "discount_rate", "npv_low": 1.0, "npv_high": 2.0}]
        },
    }


def test_review_queue_lifecycle(tmp_path: Path) -> None:
    q = ReviewQueue(f"sqlite:///{tmp_path / 'r.db'}")
    assert q.enqueue("r1", [F1, F2]) == 2
    assert q.enqueue("r1", [F1]) == 0  # idempotent
    assert (
        q.act("r1", "F-GAP-01", "edit", "alice", {"severity": "high"}, "overstated")["status"]
        == "edited"
    )
    q.act("r1", "F-INEF-01", "reject", "alice", reason="duplicate")
    assert q.summary("r1") == {"edited": 1, "rejected": 1}
    out = q.reviewed_findings("r1")
    assert [f["finding_id"] for f in out] == ["F-GAP-01"]
    assert out[0]["severity"] == "high"
    assert out[0]["edited"] is True
    log = q.log("r1")
    assert [entry["action"] for entry in log] == ["edit", "reject"]
    assert log[0]["before"]["severity"] == "critical"
    assert log[0]["after"]["severity"] == "high"
    q.act("r1", "F-INEF-01", "reset", "bob")
    assert q.items("r1", "pending")[0]["finding_id"] == "F-INEF-01"
    for bad in ({"sql": "x"}, {}, {"severity": "urgent"}):
        with pytest.raises(ReviewError):
            q.act("r1", "F-GAP-01", "edit", "alice", bad)
    with pytest.raises(ReviewError, match="reviewer"):
        q.act("r1", "F-GAP-01", "accept", " ")
    with pytest.raises(ReviewError, match="unknown finding"):
        q.act("r1", "nope", "accept", "alice")


def test_citation_resolver(tmp_path: Path) -> None:
    (tmp_path / "ingest").mkdir()
    (tmp_path / "ingest" / "docs.json").write_text(
        json.dumps([{"doc_id": "LAW", "title": "GENIUS Act", "source_url": "https://x"}])
    )
    (tmp_path / "queries").mkdir()
    (tmp_path / "queries" / "q_abc.json").write_text(
        json.dumps({"metric": "manual_share", "params": {"process": "recon"}, "result_hash": "h1"})
    )
    r = CitationResolver(tmp_path, ROOT / "config")
    assert "clause 4(a)(2)" in r.describe("[doc:LAW#s4(a)(2)]")
    assert "page 3" in r.describe("[doc:LAW#p3]")
    assert "section '2. Scope'" in r.describe("[doc:LAW#s2. Scope]")
    assert "manual_share" in r.describe("[q:q_abc]")
    assert "base 0.1" in r.describe("[a:discount_rate]")
    assert r.describe("[calc]").startswith("Deterministic")
    assert r.footnote("A [q:q_abc] B [doc:LAW#p3]") == "A [^1] B [^2]"
    assert r.strip("x [q:q_abc]") == ("x", [1])


def test_build_and_export(tmp_path: Path) -> None:
    ds = build_all(_engagement(), [F1], tmp_path, ROOT / "config", {"pending": 1})
    assert [d.name for d in ds] == [
        "executive_memo",
        "findings_register",
        "roadmap_90_day",
        "roi_summary",
    ]
    md = to_markdown(ds[0])
    assert "Not legal advice".lower() in md.lower()
    assert "Reconciliation is 41.6% manual. [1] [2]" in md
    assert "## Sources" in md
    reg = to_markdown(ds[1])
    assert "F-GAP-01" in reg
    assert "F-INEF-01" not in reg
    paths = export(ds, tmp_path / "out")
    for p in paths.values():
        assert Path(p["docx"]).stat().st_size > 1000
        assert pdf_page_count(Path(p["pdf"])) >= 1
