"""Ask the data room a question from the command line (Q&A router + verifier)."""

from __future__ import annotations

import sys
import uuid

from ledgerline.agents.context import AppContext
from ledgerline.agents.router import QAAgent


def main() -> int:
    q = " ".join(sys.argv[1:]) or "What share of reconciliation steps are manual?"
    out = QAAgent(AppContext(), f"qa-{uuid.uuid4().hex[:8]}").answer(q)
    print(
        f"Q: {q}\nroute={out['route']} corpus={out['corpus']} as_of={out['as_of']} "
        f"escalated={out['escalated']} steps={out['agent_steps']} cov={out['coverage']}"
    )
    print(f"A: {out['answer']}")
    print(f"verifier={out['verifier']} latency={out['latency_ms']}ms cost=${out['cost_usd']}")
    for s in out["sentences"]:
        if s["status"] != "supported":
            print("  dropped:", s["status"], s["text"][:100], s["note"][:100])
    return 0


if __name__ == "__main__":
    sys.exit(main())
