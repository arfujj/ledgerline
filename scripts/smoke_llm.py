"""One real, cheap Claude call through the audited client (fractions of a cent on Haiku 5.5)."""

from __future__ import annotations

import sys
import uuid

from ledgerline.core.audit import JsonlAuditSink
from ledgerline.core.budget import SpendTracker
from ledgerline.core.llm import LLMClient
from ledgerline.core.llm_cache import ResponseCache
from ledgerline.core.settings import get_settings


def main() -> int:
    s = get_settings()
    if s.anthropic_api_key is None:
        print("ANTHROPIC_API_KEY not set; skipping smoke call.")
        return 0
    run_id = f"smoke-{uuid.uuid4().hex[:8]}"
    client = LLMClient(
        s,
        JsonlAuditSink(s.audit_log_path),
        SpendTracker(s.max_usd_per_run, s.max_usd_per_day, s.data_dir / "spend.json"),
        ResponseCache(s.llm_cache_path),
    )
    r = client.complete(
        run_id=run_id,
        name="smoke",
        max_tokens=64,
        messages=[{"role": "user", "content": "Reply with the single word: ready"}],
    )
    print(f"run={run_id} model={r.model} text={r.text!r} cost=${r.cost_usd:.6f} cached={r.cached}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
