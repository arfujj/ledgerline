"""Process-map discovery. Uses PM4Py (optional `mining` extra, AGPL) when installed;
otherwise falls back to the SQL directly-follows graph, which is always available."""

from __future__ import annotations

from typing import Any

import duckdb

from ledgerline.process.metrics import ProcessMetrics


def process_map(pm: ProcessMetrics, process: str, min_edge_share: float = 0.01) -> dict[str, Any]:
    dfg = pm.run("dfg", process)
    stats = {r["activity"]: r for r in pm.run("activity_stats", process).records()}
    total = max((r["frequency"] for r in dfg.records()), default=1)
    edges = [r for r in dfg.records() if r["frequency"] / total >= min_edge_share]
    out: dict[str, Any] = {
        "process": process,
        "nodes": [{"id": a, **s} for a, s in stats.items()],
        "edges": edges,
        "query_ids": [dfg.query_id],
        "engine": "sql-dfg",
    }
    try:
        import pm4py
    except ImportError:
        return out
    con = duckdb.connect(str(pm.db_path), read_only=True)
    try:
        df = con.execute(
            "SELECT case_id, activity, timestamp FROM events WHERE "
            "process_key = ? ORDER BY case_id, timestamp",
            [process],
        ).df()
    finally:
        con.close()
    import pm4py

    log = pm4py.format_dataframe(
        df, case_id="case_id", activity_key="activity", timestamp_key="timestamp"
    )
    tree = pm4py.discover_process_tree_inductive(log, noise_threshold=0.2)
    out["process_tree"] = str(tree)
    out["engine"] = "pm4py-inductive"
    return out
