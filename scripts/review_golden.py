"""Interactive review of golden candidates: [a]ccept, [e]dit, [r]eject, [s]kip, [q]uit.

Resumable: decisions are appended to evals/golden/{approved,rejected}.jsonl and every edit is
logged to evals/golden/review_log.jsonl.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

G = Path(__file__).resolve().parents[1] / "evals" / "golden"


def _load(p: Path) -> list[dict[str, object]]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def _append(p: Path, obj: dict[str, object]) -> None:
    with p.open("a") as fh:
        fh.write(json.dumps(obj) + "\n")


def main() -> int:
    cands = _load(G / "candidates.jsonl")
    done = {c["qid"] for c in _load(G / "approved.jsonl") + _load(G / "rejected.jsonl")}
    todo = [c for c in cands if c["qid"] not in done]
    print(f"{len(todo)} to review ({len(done)} already reviewed). Ctrl-C or q to stop.\n")
    for c in todo:
        print("=" * 80)
        print(f"[{c['qid']}] type={c['type']} source={c.get('source')} as_of={c.get('as_of', '')}")
        print(f"Q: {c['question']}\nA: {c['answer']}\nGold: {c.get('gold')}")
        if c.get("numeric"):
            print(f"Numeric: {c['numeric']}")
        choice = input("[a]ccept [e]dit [r]eject [s]kip [q]uit > ").strip().lower()
        if choice == "q":
            break
        if choice == "s":
            continue
        if choice == "r":
            _append(G / "rejected.jsonl", {**c, "status": "rejected"})
            continue
        if choice == "e":
            before = dict(c)
            q = input(f"question [{c['question']}]: ").strip()
            a = input(f"answer [{c['answer']}]: ").strip()
            c = {**c, "question": q or c["question"], "answer": a or c["answer"]}
            _append(
                G / "review_log.jsonl",
                {
                    "qid": c["qid"],
                    "ts": datetime.now(UTC).isoformat(),
                    "before": before,
                    "after": c,
                },
            )
        _append(G / "approved.jsonl", {**c, "status": "approved"})
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
