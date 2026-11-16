"""Generate golden Q&A *candidates* for human review (scripts/review_golden.py).

* LLM candidates (fact, table, multi-hop, temporal, unanswerable) come from Claude Haiku 5.5
  through the Message Batches API (50% off), with structured JSON output.
* Template candidates (numeric, visual, temporal status) are built deterministically from
  eval-side ground truth (answer key + corpus manifest). The app never sees these.

Usage:
  uv run python scripts/generate_golden.py --dry-run     # plan + cost estimate, no API calls
  uv run python scripts/generate_golden.py               # submit batch, wait, write candidates
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ledgerline.core.audit import AuditEvent, JsonlAuditSink
from ledgerline.core.budget import SpendTracker
from ledgerline.core.models_registry import PROFILES, cost_usd
from ledgerline.core.settings import get_settings
from ledgerline.ingest.pipeline import load_chunks

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "golden" / "candidates.jsonl"
ANSWER_KEY = ROOT / "dataroom" / ("_answer" + "_key.json")  # eval-side only
SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "anchor": {"type": "string"},
                    "anchor_doc": {"type": "string"},
                },
                "required": ["question", "answer", "anchor", "anchor_doc"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}
SYSTEM = (
    "You write evaluation questions for a retrieval-augmented consulting assistant that "
    "analyses a (fictional) fintech client's data room and public regulations. Questions must "
    "sound like what a consultant or compliance officer would ask, must not copy long phrases "
    "from the source, and must be answerable ONLY from the given excerpt(s) unless told "
    "otherwise. For each item give a concise answer, and an `anchor`: an exact, verbatim span "
    "of 3-12 words copied from the excerpt that contains the key evidence, plus `anchor_doc`, "
    "the doc_id of the excerpt the anchor comes from."
)
PROMPTS = {
    "fact": "Write {n} factual question(s) answerable from this excerpt.",
    "table": "Write {n} question(s) that require reading values from the table in this excerpt.",
    "multi_hop": (
        "Write {n} question(s) whose answer requires combining BOTH excerpts (e.g. "
        "does the client's document meet the regulatory requirement?). Use an anchor "
        "from the regulatory excerpt."
    ),
    "temporal": (
        "Write {n} question(s) about what this regulatory text required or proposed "
        "as of a specific date. Include the as-of date in the question (between the "
        "document's publication date and today, 2026-11-16)."
    ),
    "unanswerable": (
        "Write {n} realistic question(s) a consultant might ask about this client "
        "whose answer is NOT in the excerpt or any typical data room document "
        "listed. Answer each with 'insufficient evidence'. Set anchor to '' and "
        "anchor_doc to ''."
    ),
}


def _excerpt(c: Any) -> str:
    return f'<excerpt doc_id="{c.doc_id}">\n{c.header}\n{c.text}\n</excerpt>'


def plan(seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    chunks = [c for c in load_chunks(ROOT / "data" / "ingest" / "chunks.jsonl") if c.trusted]
    room_text = [
        c for c in chunks if c.corpus == "dataroom" and c.kind == "text" and len(c.text) > 250
    ]
    room_tab = [c for c in chunks if c.corpus == "dataroom" and c.kind == "table"]
    reg_text = [c for c in chunks if c.corpus == "regulatory" and c.clause and len(c.text) > 300]
    reg_tab = [c for c in chunks if c.corpus == "regulatory" and c.kind == "table"]
    temporal = [
        c for c in reg_text if c.lineage_id in ("occ-genius-issuer-rule", "fincen-aml-program-rule")
    ]
    reqs: list[dict[str, Any]] = []

    def add(kind: str, excerpts: list[Any], n: int = 1) -> None:
        reqs.append(
            {
                "custom_id": f"{kind}-{len(reqs):04d}",
                "type": kind,
                "excerpts": [c.chunk_id for c in excerpts],
                "prompt": PROMPTS[kind].format(n=n)
                + "\n\n"
                + "\n\n".join(_excerpt(c) for c in excerpts),
            }
        )

    for c in rng.sample(room_text, min(40, len(room_text))):
        add("fact", [c], n=2)
    for c in rng.sample(reg_text, min(30, len(reg_text))):
        add("fact", [c], n=2)
    for c in rng.sample(room_tab, min(25, len(room_tab))) + rng.sample(
        reg_tab, min(10, len(reg_tab))
    ):
        add("table", [c])
    policy = [c for c in room_text if c.doc_type in ("policy", "sop", "contract")]
    for _ in range(30):
        add("multi_hop", [rng.choice(policy), rng.choice(reg_text)])
    for c in rng.sample(temporal, min(12, len(temporal))):
        add("temporal", [c], n=2)
    titles = sorted({c.title for c in chunks if c.corpus == "dataroom"})
    for i in range(10):
        reqs.append(
            {
                "custom_id": f"unanswerable-{len(reqs):04d}",
                "type": "unanswerable",
                "excerpts": [],
                "prompt": PROMPTS["unanswerable"].format(n=3)
                + f"\n\nData room documents: {'; '.join(titles)}\nVariation seed: {i}",
            }
        )
    return reqs


def template_candidates() -> list[dict[str, Any]]:
    """Deterministic numeric / visual / temporal-status candidates from eval-side truth."""
    key = json.loads(ANSWER_KEY.read_text())
    mm = key["measured_metrics"]
    out: list[dict[str, Any]] = []

    def num(q: str, metric: str, value: float, tol: float, unit: str) -> None:
        out.append(
            {
                "type": "numeric",
                "question": q,
                "answer": f"{value}{unit}",
                "numeric": {"metric": metric, "value": value, "tolerance": tol},
                "gold": [],
                "source": "template",
            }
        )

    num(
        "What share of daily reconciliation steps are performed manually?",
        "recon_manual_share",
        mm["recon_manual_share"],
        0.02,
        " (fraction of steps)",
    )
    num(
        "What percentage of KYC applications go through a request-for-more-information loop?",
        "kyc_rework_rate",
        mm["kyc_rework_rate"],
        0.02,
        " (fraction of cases)",
    )
    num(
        "What is the median wait before an EDD review starts after a potential sanctions match?",
        "kyc_edd_median_wait_h",
        mm["kyc_edd_median_wait_h"],
        3.0,
        " hours",
    )
    num(
        "What fraction of card disputes took longer than 45 days to resolve in Jan-Sep 2026?",
        "dispute_sla_breach_rate",
        mm["dispute_sla_breach_rate"],
        0.02,
        "",
    )
    num(
        "What fraction of disputes received provisional credit after 10 business days?",
        "dispute_late_pc_rate",
        mm["dispute_late_pc_rate"],
        0.02,
        "",
    )
    num(
        "How many analyst hours went to manual reconciliation steps in Jan-Sep 2026?",
        "recon_manual_hours_total",
        mm["recon_manual_hours_total"],
        mm["recon_manual_hours_total"] * 0.05,
        " hours",
    )
    num(
        "How many KYC applications were received between January and September 2026?",
        "kyc_cases",
        mm["kyc_cases"],
        0,
        "",
    )
    num(
        "How many card disputes were filed between January and September 2026?",
        "dispute_cases",
        mm["dispute_cases"],
        0,
        "",
    )
    num(
        "How many people perform enhanced due diligence reviews?",
        "edd_reviewers",
        len(mm["kyc_edd_reviewers"]),
        0,
        "",
    )
    num(
        "What is the average number of specialist handoffs per dispute?",
        "dispute_avg_handoffs",
        mm["dispute_avg_handoffs"],
        0.2,
        "",
    )
    months = mm["months"]
    for i in (2, 4, 7, 8):
        out.append(
            {
                "type": "visual",
                "question": f"According to the Q3 2026 board deck chart, what share of "
                f"disputes filed in {months[i]} were resolved after 45 days?",
                "answer": f"{mm['dispute_breach_pct_by_month'][i]:.0f}%",
                "numeric": {
                    "metric": f"dispute_breach_pct_{months[i]}",
                    "value": round(mm["dispute_breach_pct_by_month"][i]),
                    "tolerance": 1,
                },
                "gold": [{"doc_id": "BRD-2026-Q3", "anchor": ""}],
                "source": "template",
            }
        )
    for i in (0, 5, 8):
        out.append(
            {
                "type": "visual",
                "question": f"Per the board deck, how many KYC applications were received "
                f"in {months[i]} 2026?",
                "answer": str(mm["kyc_by_month"][i]),
                "numeric": {
                    "metric": f"kyc_{months[i]}",
                    "value": mm["kyc_by_month"][i],
                    "tolerance": 0,
                },
                "gold": [{"doc_id": "BRD-2026-Q3", "anchor": ""}],
                "source": "template",
            }
        )
    out.append(
        {
            "type": "visual",
            "question": "What share of NovaUSD reserves is planned to be "
            "held in Treasury bills at launch?",
            "answer": "80%",
            "numeric": {"metric": "reserve_tbill_share", "value": 80, "tolerance": 0},
            "gold": [{"doc_id": "BRD-2026-Q3", "anchor": ""}],
            "source": "template",
        }
    )
    man = json.loads((ROOT / "corpus" / "regulatory" / "manifest.json").read_text())["docs"]
    by = {d["doc_id"]: d for d in man}
    status_qs = [
        (
            "FR-2026-04089",
            "FR-2026-21706",
            "the OCC rule implementing the GENIUS Act for OCC-supervised stablecoin issuers",
        ),
        ("FR-2024-14414", "FR-2026-07033", "FinCEN's proposed AML/CFT program rule"),
    ]
    for old, new, label in status_qs:
        if old not in by or new not in by:
            continue
        o, n = by[old], by[new]
        o_pub = date.fromisoformat(o["publication_date"])
        n_pub = date.fromisoformat(n["publication_date"])
        n_eff = date.fromisoformat(n["effective_date"]) if n.get("effective_date") else None
        probes: list[tuple[date, str, str]] = []
        d = (
            date(o_pub.year, o_pub.month, 15)
            if o_pub.day <= 15
            else date(o_pub.year + (o_pub.month == 12), o_pub.month % 12 + 1, 15)
        )
        end = date(2027, 6, 15)
        step = 0
        while d <= end:
            if d < n_pub:
                gold_doc, status = old, "proposed rule"
            elif n_eff and d < n_eff:
                gold_doc, status = new, "adopted, not yet effective"
            else:
                gold_doc, status = (
                    new,
                    (
                        "final rule in effect"
                        if n["doc_type"] == "final_rule"
                        else "current proposal"
                    ),
                )
            if step % 2 == 0 or gold_doc == new:
                probes.append((d, gold_doc, status))
            step += 1
            d = date(d.year + (d.month == 12), d.month % 12 + 1, 15)
        for as_of, gold_doc, status in probes:
            out.append(
                {
                    "type": "temporal",
                    "as_of": as_of.isoformat(),
                    "question": f"As of {as_of:%B %d, %Y}, which version of {label} governs, "
                    "and what is its status?",
                    "answer": f"{by[gold_doc]['title'][:80]} ({gold_doc}; {status})",
                    "gold": [{"doc_id": gold_doc, "anchor": ""}],
                    "source": "template",
                }
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()
    s = get_settings()
    model = PROFILES[s.model_profile].judge  # Haiku 5.5 in both profiles
    reqs = plan(args.seed)
    templ = template_candidates()
    in_tok = sum(len(r["prompt"]) + len(SYSTEM) for r in reqs) / 3.5
    est = cost_usd(model, int(in_tok), 600 * len(reqs)) * 0.5  # batch discount
    print(
        f"LLM requests={len(reqs)} template candidates={len(templ)} model={model} "
        f"estimated batch cost ~${est:.3f}"
    )
    if args.dry_run:
        return 0
    if not s.llm_configured():
        print("No LLM key set; writing template candidates only.")
        _write(templ, [])
        return 0
    if s.resolved_provider() == "openrouter":
        llm = _generate_sync(reqs, s)
        _write(templ, llm)
        return 0
    spend = SpendTracker(s.max_usd_per_run, s.max_usd_per_day, s.data_dir / "spend.json")
    spend.check("golden-gen", est)
    import anthropic

    client = anthropic.Anthropic(api_key=s.anthropic_api_key.get_secret_value())
    batch = client.messages.batches.create(
        requests=[
            {
                "custom_id": r["custom_id"],
                "params": {
                    "model": model,
                    "max_tokens": 2000,
                    "system": SYSTEM,
                    "output_config": {
                        "effort": "low",
                        "format": {"type": "json_schema", "schema": SCHEMA},
                    },
                    "messages": [{"role": "user", "content": r["prompt"]}],
                },
            }
            for r in reqs
        ]
    )
    print(f"batch {batch.id} submitted")
    while client.messages.batches.retrieve(batch.id).processing_status != "ended":
        time.sleep(30)
    by_id = {r["custom_id"]: r for r in reqs}
    llm: list[dict[str, Any]] = []
    total = 0.0
    for res in client.messages.batches.results(batch.id):
        if res.result.type != "succeeded":
            continue
        msg = res.result.message
        u = msg.usage
        total += cost_usd(model, u.input_tokens, u.output_tokens) * 0.5
        text = next((b.text for b in msg.content if b.type == "text"), "{}")
        req = by_id[res.custom_id]
        for item in json.loads(text).get("items", []):
            llm.append(
                {
                    "type": req["type"],
                    "question": item["question"],
                    "answer": item["answer"],
                    "source": "llm",
                    "excerpts": req["excerpts"],
                    "gold": (
                        [{"doc_id": item["anchor_doc"], "anchor": item["anchor"]}]
                        if item["anchor"]
                        else []
                    ),
                    "unanswerable": req["type"] == "unanswerable",
                }
            )
    spend.record("golden-gen", total)
    JsonlAuditSink(s.audit_log_path).write(
        AuditEvent(
            run_id="golden-gen",
            kind="llm_call",
            name="golden_batch",
            model=model,
            cost_usd=total,
            payload={"batch_id": batch.id, "requests": len(reqs), "candidates": len(llm)},
        )
    )
    _write(templ, llm)
    print(f"wrote {len(templ) + len(llm)} candidates; actual cost ${total:.4f}")
    return 0


class _Item(BaseModel):
    question: str
    answer: str
    anchor: str
    anchor_doc: str


class _Items(BaseModel):
    items: list[_Item]


def _generate_sync(reqs: list[dict[str, Any]], s: Any) -> list[dict[str, Any]]:
    """Concurrent synchronous calls through the audited LLM client (used for OpenRouter)."""
    from concurrent.futures import ThreadPoolExecutor

    from ledgerline.core.llm import LLMClient
    from ledgerline.core.llm_cache import ResponseCache

    client = LLMClient(
        s,
        JsonlAuditSink(s.audit_log_path),
        SpendTracker(s.max_usd_per_run, s.max_usd_per_day, s.data_dir / "spend.json"),
        ResponseCache(s.llm_cache_path),
    )

    def one(r: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            res = client.complete(
                run_id="golden-gen",
                name=f"golden:{r['type']}",
                system=SYSTEM,
                max_tokens=2000,
                output_model=_Items,
                model=client.profile.judge,
                messages=[{"role": "user", "content": r["prompt"]}],
            )
        except Exception as exc:
            print(f"  {r['custom_id']} failed: {type(exc).__name__}: {exc}"[:200])
            return []
        items = res.parsed.items if res.parsed else []
        return [
            {
                "type": r["type"],
                "question": it.question,
                "answer": it.answer,
                "source": "llm",
                "excerpts": r["excerpts"],
                "gold": ([{"doc_id": it.anchor_doc, "anchor": it.anchor}] if it.anchor else []),
                "unanswerable": r["type"] == "unanswerable",
            }
            for it in items
        ]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, reqs))
    spent = client.spend.run_spend("golden-gen")
    print(f"generated via {client.provider}; spent ${spent:.4f}")
    return [x for batch in results for x in batch]


def _write(templ: list[dict[str, Any]], llm: list[dict[str, Any]]) -> None:
    chunks = {c.chunk_id: c for c in load_chunks(ROOT / "data" / "ingest" / "chunks.jsonl")}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with OUT.open("w") as fh:
        for i, cand in enumerate(templ + llm):
            # Drop LLM items whose anchor is not verbatim in a cited excerpt.
            if cand.get("source") == "llm" and cand["gold"]:
                g = cand["gold"][0]
                texts = [chunks[x].text for x in cand["excerpts"] if x in chunks]
                if not any(
                    " ".join(g["anchor"].split()).lower() in " ".join(t.split()).lower()
                    for t in texts
                ):
                    continue
            cand["qid"] = f"G{i:04d}"
            cand["status"] = "candidate"
            fh.write(json.dumps(cand) + "\n")
            kept += 1
    print(f"candidates written: {kept} -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
