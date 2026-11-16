"""Score findings against the seeded answer key (eval-only; the app never reads the key).

Matching rule (deterministic): a finding matches a key item when
  * gaps: it cites at least one of the item's evidence documents;
  * inefficiencies: it cites at least one [q:...] data query;
  AND its title/rationale/recommendation mentions one of the item's distinctive keywords.
Precision = findings matching any key item / findings considered (a lower bound, since real
but unseeded findings count against it). Recall = key items matched / key items.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _docs(cites: list[str]) -> set[str]:
    return {c.split("#")[0].removeprefix("[doc:").removeprefix("[") for c in cites}


def matches(finding: dict[str, Any], item: dict[str, Any]) -> bool:
    cites = finding.get("evidence_citations", []) + finding.get("requirement_citations", [])
    if item.get("category") == "inefficiency":
        # Inefficiencies are evidenced by event-log data: require a [q:...] query citation.
        if not any(c.startswith("[q:") for c in cites):
            return False
    else:
        kdocs = {e["doc_id"] for e in item.get("evidence", [])}
        if kdocs and not (_docs(cites) & kdocs):
            return False
    text = " ".join(
        [finding.get("title", ""), finding.get("rationale", ""), finding.get("recommendation", "")]
    ).lower()
    return any(k.lower() in text for k in item["match_keywords"])


def score(
    findings: list[dict[str, Any]], items: list[dict[str, Any]], min_confidence: float = 0.0
) -> dict[str, Any]:
    fs = [f for f in findings if f.get("confidence", 1.0) >= min_confidence]
    tp_findings = [f for f in fs if any(matches(f, i) for i in items)]
    matched: dict[str, dict[str, Any]] = {}
    for i in items:
        cands = [f for f in fs if matches(f, i)]
        if cands:
            matched[i["id"]] = min(cands, key=lambda f: SEV[f["severity"]])
    exact = sum(matched[i["id"]]["severity"] == i["severity"] for i in items if i["id"] in matched)
    within1 = sum(
        abs(SEV[matched[i["id"]]["severity"]] - SEV[i["severity"]]) <= 1
        for i in items
        if i["id"] in matched
    )
    n = len(matched)
    return {
        "findings": len(fs),
        "key_items": len(items),
        "precision": round(len(tp_findings) / len(fs), 4) if fs else 0.0,
        "recall": round(n / len(items), 4) if items else 0.0,
        "severity_exact": round(exact / n, 4) if n else 0.0,
        "severity_within_one": round(within1 / n, 4) if n else 0.0,
        "matched": {k: v["finding_id"] for k, v in matched.items()},
        "missed": [i["id"] for i in items if i["id"] not in matched],
        "unmatched_findings": [f["finding_id"] for f in fs if f not in tp_findings],
    }


def main() -> int:
    key = json.loads((ROOT / "dataroom" / ("_answer" + "_key.json")).read_text())
    gaps_path = ROOT / "data" / "graph" / "gap_findings.json"
    out: dict[str, Any] = {}
    if gaps_path.exists():
        findings = json.loads(gaps_path.read_text())
        out["gaps_all"] = score(findings, key["gaps"])
        out["gaps_conf_ge_0.6"] = score(findings, key["gaps"], 0.6)
    eng = ROOT / "data" / "engagement" / "findings.json"
    if eng.exists():
        ef = json.loads(eng.read_text())
        out["engagement_gaps"] = score(
            [f for f in ef if f["category"] == "compliance_gap"], key["gaps"]
        )
        out["engagement_inefficiencies"] = score(
            [f for f in ef if f["category"] == "inefficiency"], key["inefficiencies"]
        )
    (ROOT / "evals" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "evals" / "results" / "answer_key.json").write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        print(
            k,
            {
                x: v[x]
                for x in (
                    "findings",
                    "precision",
                    "recall",
                    "severity_exact",
                    "severity_within_one",
                    "missed",
                )
            },
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
