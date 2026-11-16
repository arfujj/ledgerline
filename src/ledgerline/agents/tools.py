"""Agent tools with per-stage allow-lists. Every tool returns Evidence with citations."""

from __future__ import annotations

import ast
import operator
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from ledgerline.agents.context import AppContext
from ledgerline.agents.evidence import Evidence
from ledgerline.core.audit import AuditEvent
from ledgerline.retrieval.temporal import diff_versions, version_as_of


class ToolNotAllowed(PermissionError):
    pass


_OPS: dict[type, Callable[..., float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Mod: operator.mod,
}


def safe_eval(expr: str) -> float:
    """Arithmetic only: numbers and + - * / ** %, parentheses. No names, calls or attributes."""

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            if isinstance(node.op, ast.Pow) and abs(ev(node.right)) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError(f"disallowed expression element: {type(node).__name__}")

    return ev(ast.parse(expr.replace(",", ""), mode="eval"))


# Anthropic tool schemas (also used by the MCP server and docs).
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "hybrid_search",
        "description": "Search the client data room and regulatory corpus "
        "(dense+BM25). Use corpus='dataroom' for client documents, 'regulatory' for law/rules. "
        "Pass as_of (YYYY-MM-DD) to get the version of regulations that governed on that date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "corpus": {"type": "string", "enum": ["dataroom", "regulatory", "any"]},
                "as_of": {"type": "string"},
                "k": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "visual_search",
        "description": "Search rendered pages (charts, tables, board "
        "decks) visually. Use for numbers shown only in charts.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
            "required": ["query"],
        },
    },
    {
        "name": "process_metrics",
        "description": "Run a whitelisted process-mining metric over "
        "event logs (kyc, disputes, recon) or support tickets. Metrics: case_count, cycle_time, "
        "sla_breach, activity_stats, manual_share, rework_rate, activity_case_share, variants, "
        "handoffs, resource_load, bottlenecks, dfg, monthly_volume, late_step, ticket_categories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "process": {"type": "string"},
                "activity": {"type": "string"},
                "threshold_hours": {"type": "number"},
                "business_days": {"type": "integer"},
                "top_n": {"type": "integer"},
            },
            "required": ["metric"],
        },
    },
    {
        "name": "graph_query",
        "description": "Query the compliance knowledge graph: kind="
        "'gaps' (requirements without satisfying controls), 'requirements' or 'controls' "
        "(optionally filtered by topic), 'vendors'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["gaps", "requirements", "controls", "vendors"]},
                "topic": {"type": "string"},
            },
            "required": ["kind"],
        },
    },
    {
        "name": "diff_versions",
        "description": "Explain what changed between a proposed and a "
        "final version of a rule (lineage_id, e.g. 'occ-genius-issuer-rule').",
        "input_schema": {
            "type": "object",
            "properties": {"lineage_id": {"type": "string"}, "max_changes": {"type": "integer"}},
            "required": ["lineage_id"],
        },
    },
    {
        "name": "version_as_of",
        "description": "Which version of a rulemaking governed on a date "
        "and its legal status (proposed / adopted not effective / effective).",
        "input_schema": {
            "type": "object",
            "properties": {"lineage_id": {"type": "string"}, "as_of": {"type": "string"}},
            "required": ["lineage_id", "as_of"],
        },
    },
    {
        "name": "roi_model",
        "description": "Run the transparent ROI model for automation "
        "opportunities; scenario low/base/high.",
        "input_schema": {
            "type": "object",
            "properties": {"scenario": {"type": "string", "enum": ["low", "base", "high"]}},
        },
    },
    {
        "name": "calculator",
        "description": "Evaluate an arithmetic expression exactly.",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
]


class ToolRegistry:
    def __init__(
        self,
        ctx: AppContext,
        run_id: str,
        allowlist_path: Path = Path("config/stage_tool_allowlist.yaml"),
    ) -> None:
        self.ctx = ctx
        self.run_id = run_id
        self.allow: dict[str, list[str]] = yaml.safe_load(allowlist_path.read_text())["stages"]
        self._impl: dict[str, Callable[..., list[Evidence]]] = {
            "hybrid_search": self.hybrid_search,
            "visual_search": self.visual_search,
            "process_metrics": self.process_metrics,
            "graph_query": self.graph_query,
            "diff_versions": self.diff_versions,
            "version_as_of": self.version_as_of,
            "roi_model": self.roi_model,
            "calculator": self.calculator,
        }

    def schemas(self, stage: str) -> list[dict[str, Any]]:
        allowed = set(self.allow.get(stage, []))
        return [s for s in TOOL_SCHEMAS if s["name"] in allowed]

    def call(self, stage: str, name: str, args: dict[str, Any]) -> list[Evidence]:
        if name not in self.allow.get(stage, []):
            self._audit(stage, name, args, 0, error="not_allowed")
            raise ToolNotAllowed(f"Tool {name!r} is not allowed in stage {stage!r}")
        if name not in self._impl:
            raise ToolNotAllowed(f"Unknown tool {name!r}")
        t0 = time.perf_counter()
        try:
            out = self._impl[name](**args)
        except Exception as exc:
            self._audit(
                stage,
                name,
                args,
                (time.perf_counter() - t0) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        self._audit(
            stage,
            name,
            args,
            (time.perf_counter() - t0) * 1000,
            n=len(out),
            cites=[c for e in out for c in e.cites][:20],
        )
        return out

    def _audit(
        self, stage: str, name: str, args: dict[str, Any], ms: float, **payload: Any
    ) -> None:
        self.ctx.audit.write(
            AuditEvent(
                run_id=self.run_id,
                kind="tool_call",
                stage=stage,
                name=name,
                latency_ms=ms,
                payload={"args": args, **payload},
            )
        )

    # --- tools ---------------------------------------------------------------------------
    def hybrid_search(
        self, query: str, corpus: str = "any", as_of: str | None = None, k: int = 6
    ) -> list[Evidence]:
        hits = self.ctx.store.search(
            query,
            k=k,
            corpus=None if corpus == "any" else corpus,
            as_of=date.fromisoformat(as_of) if as_of else None,
        )
        out = []
        for h in hits:
            c = h.chunk
            out.append(
                Evidence(
                    kind="doc",
                    text=f"{c.header}\n{c.text}",
                    cites=[f"[doc:{c.doc_id}#{c.locator()}]"],
                    trusted=c.trusted,
                    meta={"doc_id": c.doc_id, "chunk_id": c.chunk_id, "score": f"{h.score:.4f}"},
                )
            )
        return out

    def visual_search(self, query: str, k: int = 3) -> list[Evidence]:
        from ledgerline.retrieval.visual import visual_search

        return visual_search(self.ctx, query, k)

    def process_metrics(
        self, metric: str, process: str | None = None, **params: Any
    ) -> list[Evidence]:
        res = self.ctx.process.run(metric, process, **params)
        rows = res.records()[:15]
        text = f"Metric {metric} for {process or 'tickets'} (params {res.params}): " + "; ".join(
            ", ".join(f"{k}={v}" for k, v in r.items()) for r in rows
        )
        return [
            Evidence(kind="query", text=text, cites=[res.cite()], meta={"query_id": res.query_id})
        ]

    def graph_query(self, kind: str, topic: str | None = None) -> list[Evidence]:
        if kind == "gaps":
            items = self.ctx.graph_findings()
            if topic:
                items = [f for f in items if topic in f.get("topics", [])]
            return [
                Evidence(
                    kind="finding",
                    text=f"{f['title']} [{f['severity']}]: "
                    f"{f['rationale']} Recommendation: {f['recommendation']}",
                    cites=(f["requirement_citations"][:2] + f["evidence_citations"][:3])
                    or ["[doc:none#s-]"],
                    meta={"finding_id": f["finding_id"]},
                )
                for f in items[:12]
            ]
        name = {"requirements": "requirements", "controls": "controls"}.get(kind)
        if name:
            items = self.ctx.graph_items(name)
            if topic:
                items = [x for x in items if topic in x.get("topics", [])]
            out = []
            for x in items[:12]:
                p = x["prov"]
                loc = (
                    f"s{p['clause']}"
                    if p.get("clause")
                    else (
                        f"p{p['page']}" if p.get("page") is not None else f"s{p.get('section', '')}"
                    )
                )
                out.append(
                    Evidence(kind="doc", text=x["text"], cites=[f"[doc:{p['doc_id']}#{loc}]"])
                )
            return out
        if kind == "vendors":
            vend = [c for c in self.ctx.chunks if c.doc_id == "REG-VND-2026" and c.kind == "table"]
            return [
                Evidence(kind="doc", text=c.text, cites=[f"[doc:{c.doc_id}#{c.locator()}]"])
                for c in vend
            ]
        raise ValueError(f"unknown graph_query kind {kind!r}")

    def diff_versions(self, lineage_id: str, max_changes: int = 8) -> list[Evidence]:
        docs = sorted(
            (d for d in self.ctx.manifest.docs if d.lineage_id == lineage_id),
            key=lambda d: d.publication_date or date.min,
        )
        if len(docs) < 2:
            raise ValueError(f"lineage {lineage_id!r} has fewer than two versions")
        old, new = docs[-2], docs[-1]
        d = diff_versions(self.ctx.chunks, old.doc_id, new.doc_id, lineage_id)
        out = [
            Evidence(
                kind="computation",
                text=f"Diff {old.doc_id} ({old.doc_type}, "
                f"{old.publication_date}) -> {new.doc_id} ({new.doc_type}, "
                f"{new.publication_date}): sections {d.counts()}",
                cites=[
                    f"[doc:{old.doc_id}#p{_first_page(self.ctx, old.doc_id)}]",
                    f"[doc:{new.doc_id}#p{_first_page(self.ctx, new.doc_id)}]",
                ],
            )
        ]
        mods = sorted(
            (c for c in d.changes if c.change != "unchanged"), key=lambda c: c.similarity
        )[:max_changes]
        for c in mods:
            out.append(
                Evidence(
                    kind="computation",
                    text=f"§{c.section} {c.change} (similarity {c.similarity}): "
                    + " ".join(c.diff[:4])[:700],
                    cites=[x for x in (c.old_cite, c.new_cite) if x],
                )
            )
        return out

    def version_as_of(self, lineage_id: str, as_of: str) -> list[Evidence]:
        v = version_as_of(self.ctx.manifest, lineage_id, date.fromisoformat(as_of))
        cites = [f"[doc:{v.doc_id}#p{_first_page(self.ctx, v.doc_id)}]"] if v.doc_id else []
        return [Evidence(kind="computation", text=v.describe(), cites=cites or ["[calc]"])]

    def roi_model(self, scenario: str = "base") -> list[Evidence]:
        res = (
            self.ctx.roi.evaluate_all(scenario)
            if scenario == "base"
            else self.ctx.roi.scenarios()[scenario]
        )
        return [
            Evidence(
                kind="computation",
                text=(
                    f"{r.id} ({r.title}): priority {r.priority}; annual hours saved "
                    f"{r.annual_hours_saved:,.0f}; annual value ${r.annual_value_usd:,.0f}; "
                    f"implementation ${r.implementation_cost_usd:,.0f}; "
                    f"NPV ${r.npv_usd:,.0f}; payback "
                    f"{r.payback_months} months; time to value {r.time_to_value_months} months; "
                    f"scenario {scenario}"
                ),
                cites=r.citations[:8],
            )
            for r in res
        ]

    def calculator(self, expression: str) -> list[Evidence]:
        val = safe_eval(expression)
        return [Evidence(kind="computation", text=f"{expression} = {val:.6g}", cites=["[calc]"])]


def _first_page(ctx: AppContext, doc_id: str | None) -> int:
    pages = [c.page for c in ctx.chunks if c.doc_id == doc_id and c.page is not None]
    return min(pages) if pages else 1
