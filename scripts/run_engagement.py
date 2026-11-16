"""Run one full engagement end to end and print the stage trace."""

from __future__ import annotations

import sys
import uuid
from typing import Any

from ledgerline.agents.context import AppContext
from ledgerline.agents.engagement import Engagement


def main() -> int:
    run_id = sys.argv[1] if len(sys.argv) > 1 else f"eng-{uuid.uuid4().hex[:8]}"

    def show(ev: dict[str, Any]) -> None:
        if ev["type"] in ("stage_start", "stage_end", "section_verified"):
            extra = {k: v for k, v in ev.items() if k not in ("type", "stage", "run_id", "ts")}
            print(f"[{ev['stage']}] {ev['type']} {extra}")

    st = Engagement(AppContext(), run_id, on_event=show).run()
    print(
        f"run={run_id} cost=${st['cost_usd']} latency={st['latency_s']}s "
        f"gaps={len(st['gaps'])} inefficiencies={len(st['inefficiencies'])} "
        f"opportunities={len(st['opportunities'])} roadmap={len(st['roadmap'])}"
    )
    for sec in st["memo"]:
        print(f"\n## {sec['title']} {sec['verifier']}\n{sec['text'][:700]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
