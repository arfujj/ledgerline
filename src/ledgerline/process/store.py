"""Build the process-analytics DuckDB file from data-room event logs and tickets.

The database is built once (write mode) and then only ever opened read-only by tools.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from ledgerline.core.paths import guard_read

LOGS = {
    "kyc": "event_logs/kyc_onboarding.parquet",
    "disputes": "event_logs/card_disputes.parquet",
    "recon": "event_logs/daily_reconciliation.parquet",
}
TICKETS = "support/support_tickets.parquet"


def build(dataroom: Path, db_path: Path) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    try:
        # Paths are passed as relation objects (no SQL string interpolation).
        for proc, rel in LOGS.items():
            con.register(f"src_{proc}", con.read_parquet(str(guard_read(dataroom / rel))))
        con.execute("""
            CREATE TABLE events AS
            SELECT 'kyc' AS process_key, * FROM src_kyc
            UNION ALL SELECT 'disputes', * FROM src_disputes
            UNION ALL SELECT 'recon', * FROM src_recon""")
        con.register("src_tickets", con.read_parquet(str(guard_read(dataroom / TICKETS))))
        con.execute("CREATE TABLE tickets AS SELECT * FROM src_tickets")
        con.execute("""
            CREATE VIEW ev AS
            SELECT *,
              row_number() OVER (PARTITION BY case_id ORDER BY timestamp, activity) AS seq,
              lag(timestamp) OVER (PARTITION BY case_id ORDER BY timestamp, activity) AS prev_ts,
              lag(activity) OVER (PARTITION BY case_id ORDER BY timestamp, activity) AS prev_act,
              lag(resource) OVER (PARTITION BY case_id ORDER BY timestamp, activity) AS prev_res,
              lag(role) OVER (PARTITION BY case_id ORDER BY timestamp, activity) AS prev_role
            FROM events""")
        con.execute("""
            CREATE VIEW cases AS
            SELECT process_key, case_id, min(timestamp) AS start_ts, max(timestamp) AS end_ts,
                   date_diff('second', min(timestamp), max(timestamp)) / 3600.0 AS duration_h,
                   count(*) AS n_events, sum(is_manual::INT) AS n_manual,
                   string_agg(activity, ' > ' ORDER BY timestamp, activity) AS variant
            FROM events GROUP BY 1, 2""")
    finally:
        con.close()
    return db_path
