"""Copy metrics from evals/report.md into README.md between METRICS markers.

`--check` exits non-zero if README is out of sync (used in CI): README numbers must come from
the eval report, never typed by hand.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "<!-- METRICS:START -->", "<!-- METRICS:END -->"


def block() -> str:
    report = (ROOT / "evals" / "report.md").read_text()
    sections = re.findall(
        r"(## (?:Retrieval ablation|Temporal|Answer-key|Guardrails)[^\n]*\n.*?)(?=\n## |\Z)",
        report,
        re.S,
    )
    body = "\n".join(s.strip() for s in sections)
    body = body.replace("](charts/", "](evals/charts/")
    stamp = re.search(r"Generated .*? UTC from commit `[^`]+`", report)
    return (
        f"{START}\n_Copied verbatim from [evals/report.md](evals/report.md) "
        f"({stamp.group(0) if stamp else 'unknown run'})._\n\n{body}\n{END}"
    )


def main() -> int:
    readme = (ROOT / "README.md").read_text()
    new_block = block()
    if START in readme:
        updated = re.sub(re.escape(START) + r".*?" + re.escape(END), new_block, readme, flags=re.S)
    else:
        updated = readme.rstrip() + "\n\n## Measured results\n\n" + new_block + "\n"
    if "--check" in sys.argv:
        if updated != readme:
            print(
                "README metrics are out of sync with evals/report.md; run "
                "`uv run python scripts/build_readme_metrics.py`."
            )
            return 1
        return 0
    (ROOT / "README.md").write_text(updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
