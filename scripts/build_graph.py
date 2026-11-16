"""Extract requirements/controls, load Neo4j, run gap analysis; write data/graph/*.json."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ledgerline.core.audit import JsonlAuditSink
from ledgerline.core.budget import SpendTracker
from ledgerline.core.llm import LLMClient
from ledgerline.core.llm_cache import ResponseCache
from ledgerline.core.settings import get_settings
from ledgerline.graph.extract import (
    control_chunks,
    extract_controls,
    extract_requirements,
    load_scope,
    parse_vendors,
    requirement_chunks,
)
from ledgerline.graph.gaps import run_gap_analysis
from ledgerline.graph.store import MemoryGraph, Neo4jGraph
from ledgerline.ingest.pipeline import load_chunks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory", action="store_true", help="use in-memory graph, not Neo4j")
    args = ap.parse_args()
    s = get_settings()
    run_id = "graph-build"
    llm = LLMClient(
        s,
        JsonlAuditSink(s.audit_log_path),
        SpendTracker(s.max_usd_per_run, s.max_usd_per_day, s.data_dir / "spend.json"),
        ResponseCache(s.llm_cache_path),
    )
    chunks = load_chunks(s.data_dir / "ingest" / "chunks.jsonl")
    scope = load_scope(Path("config/graph_scope.yaml"))
    t0 = time.time()
    req_items = requirement_chunks(chunks, scope)
    ctl_items = control_chunks(chunks, scope)
    print(f"requirement chunks={len(req_items)} control chunks={len(ctl_items)}")
    reqs = extract_requirements(llm, req_items, run_id)
    ctrls = extract_controls(llm, ctl_items, run_id)
    vendors = parse_vendors(chunks)
    graph = (
        MemoryGraph()
        if args.memory
        else Neo4jGraph(s.neo4j_uri, s.neo4j_user, s.neo4j_password.get_secret_value())
    )
    graph.reset()
    for r in reqs:
        graph.add_requirement(r)
    for c in ctrls:
        graph.add_control(c)
    for v in vendors:
        graph.add_vendor(v)
    print("extracted", graph.stats(), f"applicable reqs={sum(r.applies for r in reqs)}")
    findings, judgments = run_gap_analysis(llm, graph, run_id)
    out = s.data_dir / "graph"
    out.mkdir(parents=True, exist_ok=True)
    (out / "requirements.json").write_text(json.dumps([r.model_dump() for r in reqs], indent=1))
    (out / "controls.json").write_text(json.dumps([c.model_dump() for c in ctrls], indent=1))
    (out / "judgments.json").write_text(
        json.dumps({k: v.model_dump() for k, v in judgments.items()}, indent=1)
    )
    (out / "gap_findings.json").write_text(json.dumps([f.model_dump() for f in findings], indent=1))
    print("graph", graph.stats())
    print(
        f"findings={len(findings)} spent=${llm.spend.run_spend(run_id):.4f} "
        f"({time.time() - t0:.0f}s)"
    )
    for f in findings:
        print(f" {f.finding_id} [{f.severity}] {f.title} {f.evidence_citations[:2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
