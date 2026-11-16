"""MCP server exposing Ledgerline to Claude Desktop / Claude Code.

Tools: run_engagement, ask_dataroom, gap_check, size_opportunity, diff_regulation.
Run:  uv run python -m ledgerline.mcp_server.server            (stdio)
      uv run python -m ledgerline.mcp_server.server --http     (streamable HTTP on :8765)
All outputs are grounded in the SYNTHETIC NovaPay data room and are not legal advice.
"""

from __future__ import annotations

import sys
import uuid
from functools import lru_cache
from typing import Any

from mcp.server.mcpserver import MCPServer

server: MCPServer = MCPServer(
    "ledgerline",
    title="Ledgerline",
    instructions=(
        "Ledgerline is an AI consulting copilot for fintech AI-readiness & compliance "
        "engagements over a SYNTHETIC client data room (NovaPay). Every answer carries "
        "citations ([doc:...], [q:...], [a:...]). Outputs are not legal advice."
    ),
)


@lru_cache(maxsize=1)
def _ctx() -> Any:
    from ledgerline.agents.context import AppContext

    return AppContext()


@server.tool(
    description="Run a full engagement (discovery, process analysis, opportunity "
    "sizing, gap analysis, synthesis). Returns the verified executive "
    "summary, top findings, opportunities and cost."
)
def run_engagement() -> dict[str, Any]:
    from ledgerline.agents.engagement import Engagement

    st = Engagement(_ctx(), f"mcp-{uuid.uuid4().hex[:8]}").run()
    sev = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings = sorted(
        [f for f in st["gaps"] if f.get("confidence", 0) >= 0.6]
        + st["inefficiencies"]
        + st["security"],
        key=lambda f: sev[f["severity"]],
    )
    return {
        "run_id": st["run_id"],
        "cost_usd": st["cost_usd"],
        "latency_s": st["latency_s"],
        "executive_summary": next(
            (s["text"] for s in st["memo"] if s["title"] == "Executive summary"), ""
        ),
        "top_findings": [
            {
                k: f[k]
                for k in ("finding_id", "severity", "title", "evidence_citations", "recommendation")
            }
            for f in findings[:10]
        ],
        "opportunities": [
            {k: o[k] for k in ("id", "title", "priority", "npv_usd", "payback_months", "citations")}
            for o in st["opportunities"]
        ],
        "disclaimer": st["disclaimer"],
    }


@server.tool(
    description="Ask a question about the client data room and regulations. Uses "
    "the adaptive router (hybrid -> graph/temporal/process tools) and the "
    "grounding verifier; returns a cited answer or 'insufficient evidence'."
)
def ask_dataroom(question: str) -> dict[str, Any]:
    from ledgerline.agents.router import QAAgent

    out = QAAgent(_ctx(), f"mcp-qa-{uuid.uuid4().hex[:8]}").answer(question)
    return {
        k: out[k]
        for k in (
            "answer",
            "insufficient",
            "route",
            "as_of",
            "escalated",
            "verifier",
            "cost_usd",
            "disclaimer",
        )
    }


@server.tool(
    description="List compliance gaps from the knowledge-graph gap analysis, "
    "optionally filtered by topic (e.g. 'reserve_reporting', "
    "'ai_human_oversight', 'error_resolution_timing') and minimum severity."
)
def gap_check(topic: str = "", min_severity: str = "medium") -> list[dict[str, Any]]:
    order = ["critical", "high", "medium", "low"]
    if min_severity not in order:
        raise ValueError(f"min_severity must be one of {order}")
    keep = order[: order.index(min_severity) + 1]
    return [
        {
            k: f[k]
            for k in (
                "finding_id",
                "severity",
                "title",
                "rationale",
                "recommendation",
                "evidence_citations",
                "requirement_citations",
            )
        }
        for f in _ctx().graph_findings()
        if f["severity"] in keep and (not topic or topic in f.get("topics", []))
    ]


@server.tool(
    description="Size automation opportunities with the transparent ROI model. "
    "scenario: low | base | high. Optionally pass an opportunity id."
)
def size_opportunity(opportunity_id: str = "", scenario: str = "base") -> list[dict[str, Any]]:
    roi = _ctx().roi
    if scenario not in ("low", "base", "high"):
        raise ValueError("scenario must be low, base or high")
    res = roi.evaluate_all() if scenario == "base" else roi.scenarios()[scenario]
    out = [
        r.model_dump(exclude={"inputs"})
        for r in res
        if not opportunity_id or r.id == opportunity_id
    ]
    if opportunity_id and out:
        opp = next(o for o in roi.catalogue if o["id"] == opportunity_id)
        out[0]["sensitivity"] = [s.model_dump() for s in roi.sensitivity(opp)[:5]]
    return out


@server.tool(
    description="Explain what changed between the proposed and final versions of a "
    "rulemaking, or which version governed on an as_of date (YYYY-MM-DD). "
    "lineage_id e.g. 'occ-genius-issuer-rule', 'fincen-aml-program-rule'."
)
def diff_regulation(lineage_id: str, as_of: str = "", max_changes: int = 10) -> dict[str, Any]:
    from ledgerline.agents.tools import ToolRegistry

    reg = ToolRegistry(_ctx(), f"mcp-diff-{uuid.uuid4().hex[:6]}")
    out: dict[str, Any] = {"lineage_id": lineage_id}
    if as_of:
        out["version_as_of"] = [
            e.model_dump()
            for e in reg.call("qa", "version_as_of", {"lineage_id": lineage_id, "as_of": as_of})
        ]
    out["changes"] = [
        e.model_dump()
        for e in reg.call(
            "qa", "diff_versions", {"lineage_id": lineage_id, "max_changes": max_changes}
        )
    ]
    return out


def main() -> None:
    if "--http" in sys.argv:
        server.run(transport="streamable-http", port=8765)
    else:
        server.run()


if __name__ == "__main__":
    main()
