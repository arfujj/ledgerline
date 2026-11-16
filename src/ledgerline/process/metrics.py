"""`process_metrics` tool: whitelisted, parameterised, read-only SQL over the process DB.

Every call returns a QueryResult with a deterministic `query_id` and is persisted so that a
deliverable can cite it as [q:<query_id>] and the verifier can re-run it and compare hashes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

PROCESSES = {"kyc", "disputes", "recon"}

# Each metric: (description, SQL template). Only $named parameters are ever bound.
METRICS: dict[str, tuple[str, str]] = {
    "case_count": (
        "Number of cases",
        """
        SELECT count(*) AS cases FROM cases WHERE process_key = $process""",
    ),
    "cycle_time": (
        "Case duration percentiles in hours",
        """
        SELECT count(*) AS cases,
               round(quantile_cont(duration_h, 0.5), 1) AS p50_h,
               round(quantile_cont(duration_h, 0.9), 1) AS p90_h,
               round(avg(duration_h), 1) AS mean_h
        FROM cases WHERE process_key = $process""",
    ),
    "sla_breach": (
        "Share of cases whose duration exceeds threshold_hours",
        """
        SELECT count(*) AS cases,
               sum((duration_h > $threshold_hours)::INT) AS breached,
               round(avg((duration_h > $threshold_hours)::INT), 4) AS breach_rate
        FROM cases WHERE process_key = $process""",
    ),
    "activity_stats": (
        "Per-activity volume, manual share and median wait before it",
        """
        SELECT activity, count(*) AS events, count(DISTINCT case_id) AS cases,
               round(avg(is_manual::INT), 4) AS manual_share,
               round(median(date_diff('second', prev_ts, timestamp) / 3600.0), 2)
                   AS median_wait_h,
               round(quantile_cont(date_diff('second', prev_ts, timestamp) / 3600.0, 0.9), 2)
                   AS p90_wait_h,
               round(coalesce(sum(date_diff('second', prev_ts, timestamp)), 0) / 3600.0, 1)
                   AS total_elapsed_h
        FROM ev WHERE process_key = $process GROUP BY activity ORDER BY events DESC""",
    ),
    "manual_share": (
        "Share of process steps executed manually, and elapsed time before them",
        """
        SELECT round(avg(is_manual::INT), 4) AS manual_step_share,
               sum(is_manual::INT) AS manual_steps, count(*) AS steps,
               round(sum(CASE WHEN is_manual AND prev_ts IS NOT NULL
                         THEN date_diff('second', prev_ts, timestamp) ELSE 0 END)
                     / nullif(sum(CASE WHEN prev_ts IS NOT NULL
                              THEN date_diff('second', prev_ts, timestamp) END), 0), 4)
                   AS manual_elapsed_time_share
        FROM ev WHERE process_key = $process""",
    ),
    "rework_rate": (
        "Share of cases where an activity occurs more than once",
        """
        WITH c AS (SELECT case_id, activity, count(*) AS n FROM events
                   WHERE process_key = $process GROUP BY 1, 2)
        SELECT activity, sum((n > 1)::INT) AS cases_with_repeat,
               round(sum((n > 1)::INT) / (SELECT count(*) FROM cases
                                          WHERE process_key = $process), 4) AS rework_rate
        FROM c GROUP BY activity HAVING sum((n > 1)::INT) > 0 ORDER BY 2 DESC""",
    ),
    "activity_case_share": (
        "Share of cases that contain a given activity",
        """
        SELECT count(DISTINCT case_id) AS cases_with_activity,
               round(count(DISTINCT case_id) / (SELECT count(*) FROM cases
                                                WHERE process_key = $process), 4) AS share
        FROM events WHERE process_key = $process AND activity = $activity""",
    ),
    "variants": (
        "Most frequent process variants",
        """
        SELECT variant, count(*) AS cases,
               round(count(*) / sum(count(*)) OVER (), 4) AS share,
               round(median(duration_h), 1) AS median_h
        FROM cases WHERE process_key = $process GROUP BY variant
        ORDER BY cases DESC LIMIT $top_n""",
    ),
    "handoffs": (
        "Average human-to-human handoffs per case",
        """
        WITH h AS (SELECT case_id, sum(CASE WHEN prev_res IS NOT NULL AND resource <> prev_res
                         AND role NOT IN ('SYSTEM','CUSTOMER','AI_AGENT')
                         AND prev_role NOT IN ('SYSTEM','CUSTOMER','AI_AGENT') THEN 1 ELSE 0 END)
                         AS n
                   FROM ev WHERE process_key = $process GROUP BY case_id)
        SELECT round(avg(n), 2) AS avg_handoffs, max(n) AS max_handoffs FROM h""",
    ),
    "resource_load": (
        "Events and cases per human resource for an activity (bottlenecks)",
        """
        SELECT resource, role, count(*) AS events, count(DISTINCT case_id) AS cases,
               round(count(*) / sum(count(*)) OVER (), 4) AS share,
               round(median(date_diff('second', prev_ts, timestamp) / 3600.0), 2)
                   AS median_wait_h
        FROM ev WHERE process_key = $process AND activity = $activity
        GROUP BY resource, role ORDER BY events DESC""",
    ),
    "bottlenecks": (
        "Activities ranked by median waiting time before they start",
        """
        SELECT activity, count(*) AS events,
               round(median(date_diff('second', prev_ts, timestamp) / 3600.0), 2)
                   AS median_wait_h,
               count(DISTINCT resource) AS distinct_resources,
               round(avg(is_manual::INT), 2) AS manual_share
        FROM ev WHERE process_key = $process AND prev_ts IS NOT NULL
        GROUP BY activity ORDER BY median_wait_h DESC LIMIT $top_n""",
    ),
    "dfg": (
        "Directly-follows graph: edge frequencies and median transition hours",
        """
        SELECT prev_act AS source, activity AS target, count(*) AS frequency,
               round(median(date_diff('second', prev_ts, timestamp) / 3600.0), 2)
                   AS median_h
        FROM ev WHERE process_key = $process AND prev_act IS NOT NULL
        GROUP BY 1, 2 ORDER BY frequency DESC""",
    ),
    "monthly_volume": (
        "Cases started per month",
        """
        SELECT strftime(start_ts, '%Y-%m') AS month, count(*) AS cases,
               round(median(duration_h), 1) AS median_h
        FROM cases WHERE process_key = $process GROUP BY 1 ORDER BY 1""",
    ),
    "late_step": (
        "Share of cases where an activity occurs more than N business days after case start",
        """
        WITH s AS (SELECT c.case_id, c.start_ts, min(e.timestamp) AS t FROM cases c
                   LEFT JOIN events e ON e.case_id = c.case_id AND e.activity = $activity
                   WHERE c.process_key = $process GROUP BY 1, 2)
        SELECT count(*) AS cases,
               round(avg(CASE WHEN t IS NULL THEN 0 ELSE
                   ((date_diff('day', start_ts, t) * 5 / 7) > $business_days)::INT END), 4)
                   AS late_rate
        FROM s""",
    ),
    "ticket_categories": (
        "Support tickets by category with handle time and AI handling",
        """
        SELECT category, count(*) AS tickets,
               round(count(*) / sum(count(*)) OVER (), 4) AS share,
               round(median(handle_time_min), 1) AS median_handle_min,
               round(sum(handle_time_min) / 60.0, 1) AS total_handle_hours,
               round(avg((handled_by = 'ai_agent')::INT), 3) AS ai_share
        FROM tickets GROUP BY category ORDER BY tickets DESC""",
    ),
}
DEFAULTS: dict[str, Any] = {"top_n": 10, "threshold_hours": 45 * 24, "business_days": 10}


class MetricError(ValueError):
    pass


@dataclass
class QueryResult:
    query_id: str
    metric: str
    params: dict[str, Any]
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    result_hash: str

    def records(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, r, strict=True)) for r in self.rows]

    def cite(self) -> str:
        return f"[q:{self.query_id}]"


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


class ProcessMetrics:
    def __init__(self, db_path: Path, query_log: Path) -> None:
        self.db_path = db_path
        self.query_log = query_log
        query_log.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path), read_only=True)

    def run(self, metric: str, process: str | None = None, **params: Any) -> QueryResult:
        if metric not in METRICS:
            raise MetricError(f"Unknown metric {metric!r}. Allowed: {sorted(METRICS)}")
        _, sql = METRICS[metric]
        bind: dict[str, Any] = {}
        if "$process" in sql:
            if process not in PROCESSES:
                raise MetricError(f"process must be one of {sorted(PROCESSES)}")
            bind["process"] = process
        for name in ("threshold_hours", "top_n", "business_days", "activity"):
            if f"${name}" in sql:
                val = params.get(name, DEFAULTS.get(name))
                if val is None:
                    raise MetricError(f"metric {metric!r} requires parameter {name!r}")
                bind[name] = val
        unknown = set(params) - set(bind)
        if unknown:
            raise MetricError(f"Unexpected parameters for {metric!r}: {sorted(unknown)}")
        con = self._connect()
        try:
            cur = con.execute(sql, bind)
            columns = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchall()]
        finally:
            con.close()
        rows = [
            [float(v) if hasattr(v, "is_integer") and not isinstance(v, int) else v for v in r]
            for r in rows
        ]
        qid = "q_" + _hash({"metric": metric, "params": bind})[:12]
        res = QueryResult(qid, metric, bind, " ".join(sql.split()), columns, rows, _hash(rows)[:16])
        (self.query_log / f"{qid}.json").write_text(
            json.dumps(
                {
                    "query_id": qid,
                    "metric": metric,
                    "params": bind,
                    "sql": res.sql,
                    "columns": columns,
                    "rows": rows,
                    "result_hash": res.result_hash,
                },
                default=str,
                indent=1,
            )
        )
        return res

    def rerun(self, query_id: str) -> tuple[QueryResult, bool]:
        """Re-execute a logged query; returns (result, hash_matches)."""
        logged = json.loads((self.query_log / f"{query_id}.json").read_text())
        params = dict(logged["params"])
        process = params.pop("process", None)
        res = self.run(logged["metric"], process, **params)
        return res, res.result_hash == logged["result_hash"]

    @staticmethod
    def catalog() -> dict[str, str]:
        return {k: v[0] for k, v in METRICS.items()}
