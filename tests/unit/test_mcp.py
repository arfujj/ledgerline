from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from ledgerline.mcp_server import server as mcp_mod

FINDINGS = [
    {
        "finding_id": "F1",
        "severity": "critical",
        "title": "Reserves",
        "rationale": "r",
        "recommendation": "x",
        "evidence_citations": ["[doc:A#p1]"],
        "requirement_citations": [],
        "topics": ["reserve_rehypothecation"],
        "confidence": 0.8,
    },
    {
        "finding_id": "F2",
        "severity": "low",
        "title": "Docs",
        "rationale": "r",
        "recommendation": "x",
        "evidence_citations": [],
        "requirement_citations": [],
        "topics": ["aml_program"],
        "confidence": 0.3,
    },
]


def test_tools_registered() -> None:
    tools = asyncio.run(mcp_mod.server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "run_engagement",
        "ask_dataroom",
        "gap_check",
        "size_opportunity",
        "diff_regulation",
    }


def test_gap_check(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx: Any = SimpleNamespace(graph_findings=lambda: FINDINGS)
    monkeypatch.setattr(mcp_mod, "_ctx", lambda: ctx)
    assert [f["finding_id"] for f in mcp_mod.gap_check()] == ["F1"]
    assert [f["finding_id"] for f in mcp_mod.gap_check(min_severity="low")] == ["F1", "F2"]
    assert mcp_mod.gap_check(topic="aml_program", min_severity="low")[0]["finding_id"] == "F2"
    with pytest.raises(ValueError, match="min_severity"):
        mcp_mod.gap_check(min_severity="urgent")
