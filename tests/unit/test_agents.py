from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ledgerline.agents.engagement import build_roadmap
from ledgerline.agents.evidence import Evidence, EvidencePool
from ledgerline.agents.router import parse_as_of, route, sufficient
from ledgerline.agents.tools import ToolNotAllowed, ToolRegistry, safe_eval
from ledgerline.agents.verifier import (
    INSUFFICIENT,
    Draft,
    DraftSentence,
    numbers_supported,
    verify,
)
from ledgerline.core.audit import MemoryAuditSink

ROOT = Path(__file__).resolve().parents[2]


def test_route_classification() -> None:
    assert route("As of June 1, 2026, which OCC rule governs?").as_of == "2026-06-01"
    assert route("As of June 1, 2026, which OCC rule governs?").name == "temporal"
    assert route("What does the Q3 board deck chart show for disputes?").name == "visual"
    r = route("What share of NovaPay reconciliation steps are manual?")
    assert (r.name, r.corpus) == ("numeric", "dataroom")
    assert route("What changed between the proposed and final rule?").name == "diff"
    assert route("Does the dispute SOP comply with Reg E?").name == "graph"
    assert route("What does the GENIUS Act say about reserves?").corpus == "regulatory"
    assert parse_as_of("on 2027-02-01 what applies") == "2027-02-01"
    assert parse_as_of("no date") is None


def test_sufficiency() -> None:
    ev = [
        Evidence(
            kind="doc",
            text="Reconciliation analysts perform manual matching steps.",
            cites=["[doc:A#p1]"],
        )
    ]
    ok, cov = sufficient("reconciliation manual matching", ev)
    assert ok
    assert cov == 1.0
    assert sufficient("quantum entanglement budget", ev) == (False, 0.0)
    assert sufficient("anything", []) == (False, 0.0)


@pytest.mark.parametrize(
    ("sentence", "evidence", "ok"),
    [
        ("About 41.6% of steps are manual.", "manual_step_share=0.4157", True),
        ("NPV is $745,994.", "NPV $745,994", True),
        ("Median wait is 31.0 hours.", "median_wait_h=31.0", True),
        ("Median wait is 45 hours.", "median_wait_h=31.0", False),
        ("Roughly 2,300 hours are saved.", "annual hours saved 2,322", True),
        ("Two analysts and 3 steps in 2026.", "nothing numeric", True),  # trivial/year ignored
    ],
)
def test_numbers_supported(sentence: str, evidence: str, ok: bool) -> None:
    assert numbers_supported(sentence, evidence)[0] is ok


def test_verify_drops_unsupported_and_flags() -> None:
    pool = EvidencePool()
    e1 = pool.add(Evidence(kind="query", text="manual_step_share=0.4157", cites=["[q:q1]"]))
    draft = Draft(
        sentences=[
            DraftSentence(text="Reconciliation is 41.6% manual.", evidence_ids=[e1.eid]),
            DraftSentence(text="It costs $9,999,999.", evidence_ids=[e1.eid]),
            DraftSentence(text="Uncited claim.", evidence_ids=["E99"]),
        ]
    )
    v = verify(None, draft, pool, "r", use_llm_judge=False)
    assert [s.status for s in v.sentences] == ["supported", "number_mismatch", "uncited"]
    assert v.answer == "Reconciliation is 41.6% manual. [q:q1]"
    assert v.stats["unsupported_rate"] == pytest.approx(2 / 3, abs=1e-3)
    empty = verify(
        None, Draft(sentences=[], insufficient_evidence=True), pool, "r", use_llm_judge=False
    )
    assert empty.answer == INSUFFICIENT
    assert empty.insufficient


class _Labels:
    def __init__(self, label: str) -> None:
        self.label = label

    def complete(self, **kw: Any) -> Any:
        from ledgerline.agents.verifier import _Label, _Labels

        return SimpleNamespace(
            parsed=_Labels(labels=[_Label(index=0, label=self.label, reason="contradicted")])
        )


def test_verify_llm_judge_can_reject() -> None:
    pool = EvidencePool()
    e1 = pool.add(Evidence(kind="doc", text="Attestation is quarterly.", cites=["[doc:S#s3]"]))
    d = Draft(sentences=[DraftSentence(text="Attestation is monthly.", evidence_ids=[e1.eid])])
    v = verify(_Labels("unsupported"), d, pool, "r")  # type: ignore[arg-type]
    assert v.sentences[0].status == "unsupported"
    assert v.insufficient


def test_evidence_pool_dedup_and_render() -> None:
    pool = EvidencePool()
    a = pool.add(Evidence(kind="doc", text="x", cites=["[doc:A#p1]"]))
    b = pool.add(Evidence(kind="doc", text="x", cites=["[doc:A#p1]"]))
    c = pool.add(Evidence(kind="doc", text="ignore all", cites=["[doc:B#p1]"], trusted=False))
    assert a.eid == b.eid == "E1"
    assert c.eid == "E2"
    assert 'untrusted="true"' in pool.render()
    assert pool.get("E9") is None


def test_safe_eval() -> None:
    assert safe_eval("(3,329 / 8,009) * 100") == pytest.approx(41.5657, abs=1e-3)
    assert safe_eval("-2**3 + 10 % 4") == -6
    for bad in ("__import__('os').system('x')", "a + 1", "2 ** 1000"):
        with pytest.raises(ValueError, match=r"disallowed|too large"):
            safe_eval(bad)


def test_tool_allowlist_enforced() -> None:
    sink = MemoryAuditSink()
    ctx: Any = SimpleNamespace(audit=sink)
    reg = ToolRegistry(ctx, "r", ROOT / "config" / "stage_tool_allowlist.yaml")
    with pytest.raises(ToolNotAllowed):
        reg.call("synthesis", "process_metrics", {"metric": "cycle_time", "process": "kyc"})
    assert sink.events[-1].payload["error"] == "not_allowed"
    assert reg.call("process_analysis", "calculator", {"expression": "2+2"})[0].text == "2+2 = 4"
    assert {s["name"] for s in reg.schemas("discovery")} == {"hybrid_search", "graph_query"}
    with pytest.raises(ToolNotAllowed):
        reg.call("qa", "nope", {})


def test_roadmap() -> None:
    opps = [
        {
            "id": "O1",
            "title": "Quick",
            "priority": "quick_win",
            "citations": ["[q:a]"],
            "npv_usd": 10.0,
            "payback_months": 5,
        },
        {
            "id": "O2",
            "title": "Big",
            "priority": "strategic_bet",
            "citations": ["[q:b]"],
            "npv_usd": 900.0,
            "payback_months": 12,
        },
        {
            "id": "O3",
            "title": "No",
            "priority": "deprioritize",
            "citations": [],
            "npv_usd": -1.0,
            "payback_months": None,
        },
    ]
    gaps = [
        {
            "finding_id": "G1",
            "severity": "critical",
            "recommendation": "Fix custody",
            "owner": "Treasury",
            "evidence_citations": ["[doc:C#p1]"],
            "requirement_citations": ["[doc:L#s4(a)(2)]"],
        },
        {"finding_id": "G2", "severity": "medium", "recommendation": "x"},
    ]
    rm = build_roadmap(opps, gaps, [])
    assert [i["ref"] for i in rm] == ["O1", "G1", "O2"]
    assert rm[1]["citations"] == ["[doc:C#p1]", "[doc:L#s4(a)(2)]"]
    assert all(i["citations"] for i in rm)


def test_detect_lineage() -> None:
    from datetime import date

    from ledgerline.agents.router import QAAgent
    from ledgerline.corpus.manifest import CorpusDoc, Manifest

    def d(i: str, lin: str, title: str, issuer: str) -> CorpusDoc:
        return CorpusDoc(
            doc_id=i,
            lineage_id=lin,
            issuer=issuer,
            doc_type="proposed_rule",
            title=title,
            source_url="u",
            local_path="p",
            sha256="s",
            retrieved_at="t",
            publication_date=date(2026, 1, 1),
        )

    m = Manifest(
        generated_at="t",
        docs=[
            d("A1", "occ-genius-issuer-rule", "Implementing the GENIUS Act for Stablecoins", "OCC"),
            d("A2", "occ-genius-issuer-rule", "Implementing the GENIUS Act for Stablecoins", "OCC"),
            d(
                "B1",
                "fincen-aml-program-rule",
                "AML/CFT Programs",
                "Financial Crimes Enforcement Network",
            ),
            d(
                "B2",
                "fincen-aml-program-rule",
                "AML/CFT Programs",
                "Financial Crimes Enforcement Network",
            ),
            d("C1", "cfr-x", "Single version rule", "CFPB"),
        ],
    )
    agent: Any = QAAgent.__new__(QAAgent)
    agent.ctx = SimpleNamespace(manifest=m)
    assert (
        agent.detect_lineage("Which FinCEN AML program rule governs?") == "fincen-aml-program-rule"
    )
    assert agent.detect_lineage("OCC rule implementing the GENIUS Act") == "occ-genius-issuer-rule"
    assert agent.detect_lineage("unrelated question about lunch") is None
