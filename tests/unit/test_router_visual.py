from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ledgerline.agents.evidence import Evidence
from ledgerline.agents.router import QAAgent
from ledgerline.agents.verifier import Draft, DraftSentence, _Label, _Labels
from ledgerline.core.audit import MemoryAuditSink
from ledgerline.core.llm import ToolUse
from ledgerline.retrieval import visual


class FakeLLM:
    """Scripted LLM: first agent step calls a tool, then answers citing E1."""

    def __init__(self, insufficient_first: bool = False) -> None:
        self.calls: list[str] = []
        self.insufficient_first = insufficient_first
        self.spend = SimpleNamespace(run_spend=lambda rid: 0.0)
        self.profile = SimpleNamespace(main="fake")

    def complete(self, **kw: Any) -> Any:
        name = kw["name"]
        self.calls.append(name)
        if name == "agent_step":
            if self.calls.count("agent_step") == 1:
                return SimpleNamespace(
                    tool_uses=[
                        ToolUse(
                            id="t1",
                            name="process_metrics",
                            input={"metric": "manual_share", "process": "recon"},
                        )
                    ],
                    raw_content=[{"type": "text", "text": "calling"}],
                )
            return SimpleNamespace(tool_uses=[], raw_content=[])
        if name in ("answer", "answer_retry"):
            if self.insufficient_first and name == "answer":
                return SimpleNamespace(parsed=Draft(sentences=[], insufficient_evidence=True))
            return SimpleNamespace(
                parsed=Draft(
                    sentences=[
                        DraftSentence(
                            text="Reconciliation is 41.6% manual.", evidence_ids=["E1", "E2"]
                        )
                    ]
                )
            )
        if name == "verify_entailment":
            return SimpleNamespace(
                parsed=_Labels(labels=[_Label(index=0, label="supported", reason="ok")])
            )
        raise AssertionError(name)


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def call(self, stage: str, name: str, args: dict[str, Any]) -> list[Evidence]:
        self.calls.append((stage, name))
        if name == "process_metrics":
            return [Evidence(kind="query", text="manual_step_share=0.4157", cites=["[q:q1]"])]
        return [
            Evidence(
                kind="doc",
                text="Reconciliation uses spreadsheets.",
                cites=["[doc:SOP-REC-001#s2. Steps]"],
            )
        ]

    def schemas(self, stage: str) -> list[dict[str, Any]]:
        return []


def _agent(llm: FakeLLM) -> QAAgent:
    ctx: Any = SimpleNamespace(llm=llm, audit=MemoryAuditSink())
    agent = QAAgent.__new__(QAAgent)
    agent.__init__
    agent.ctx = ctx
    agent.run_id = "r"
    agent.tools = FakeTools()  # type: ignore[assignment]
    agent.max_steps = 3
    agent.features = frozenset({"router", "visual", "graph", "temporal", "escalate", "verify"})
    agent.verify_with_llm = True
    agent.allow_escalation = True
    agent.store = None
    agent.k = 6
    return agent


def test_numeric_question_escalates_and_verifies() -> None:
    llm = FakeLLM()
    agent = _agent(llm)
    out = agent.answer("What share of NovaPay reconciliation steps are manual?")
    assert out["route"] == "numeric"
    assert out["escalated"] is True
    assert out["agent_steps"] == 1
    assert "[q:q1]" in out["answer"]
    assert out["verifier"]["supported"] == 1.0
    assert ("qa", "process_metrics") in agent.tools.calls  # type: ignore[attr-defined]


def test_insufficient_triggers_retry_after_escalation() -> None:
    llm = FakeLLM(insufficient_first=True)
    agent = _agent(llm)
    out = agent.answer("Reconciliation spreadsheets?")
    assert "answer_retry" in llm.calls
    assert out["insufficient"] is False


def test_ablation_without_router_uses_plain_search() -> None:
    agent = _agent(FakeLLM())
    agent.features = frozenset()
    agent.allow_escalation = False
    agent.verify_with_llm = False
    out = agent.answer("What share of reconciliation steps are manual?")
    assert out["route"] == "plain"
    assert agent.tools.calls[0] == ("qa", "hybrid_search")  # type: ignore[attr-defined]


def test_visual_lexical_fallback_and_reading(tmp_path: Path, monkeypatch: Any) -> None:
    (tmp_path / "pages").mkdir()
    img = tmp_path / "pages" / "BRD_p2.png"
    img.write_bytes(b"\x89PNG fake")
    recs = [
        visual.PageRecord(
            page_id="BRD_p2",
            doc_id="BRD",
            page=2,
            image_path=str(img),
            text="Monthly KYC applications chart",
            title="Board deck",
        ),
        visual.PageRecord(
            page_id="CTR_p1",
            doc_id="CTR",
            page=1,
            image_path=str(img),
            text="Master services agreement",
            title="Contract",
        ),
    ]
    (tmp_path / "pages" / "pages.json").write_text(json.dumps([r.model_dump() for r in recs]))
    monkeypatch.setattr(visual, "visual_available", lambda: False)

    class LLM:
        def complete(self, **kw: Any) -> Any:
            assert kw["messages"][0]["content"][0]["type"] == "image"
            return SimpleNamespace(
                parsed=visual.PageReading(relevant=True, facts="Jun: 1569 applications")
            )

    ctx: Any = SimpleNamespace(settings=SimpleNamespace(data_dir=tmp_path), llm=LLM())
    pages, mode = visual.search_pages(ctx, "monthly KYC applications in June", 1)
    assert mode == "lexical_fallback"
    assert pages[0].page_id == "BRD_p2"
    ev = visual.visual_search(ctx, "monthly KYC applications in June", 1)
    assert ev[0].cites == ["[doc:BRD#p2]"]
    assert "1569" in ev[0].text
    empty: Any = SimpleNamespace(settings=SimpleNamespace(data_dir=tmp_path / "none"))
    assert visual.search_pages(empty, "x") == ([], "no_index")
