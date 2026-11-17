"""Answer-level evaluation and the ablation ladder.

Configs (each a QAAgent feature set over a retrieval collection):
  L1 naive_rag       fixed-size chunks, dense only, single LLM answer
  L2 hybrid          structure-aware chunks, dense+BM25 (no headers)
  L3 +headers        contextual chunk headers
  L4 +visual         router with the visual page path (ColPali + VLM page reading)
  L5 +graph          + compliance knowledge-graph route
  L6 +temporal       + version-aware (as-of) route
  L7 full            + agentic escalation (tool use) + grounding verifier

Metrics: answer correctness (deterministic for numeric/visual/temporal-template/unanswerable,
Claude Haiku judge vs gold answer otherwise), numeric accuracy, temporal correctness, refusal
accuracy, false-refusal rate, citation precision, hallucinated-claim rate (independent post-hoc
entailment check of the final answer against retrieved evidence, same for every config),
retrieval hit rate (gold anchor in evidence), latency p50/p95, cost per question.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import random
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from qdrant_client import QdrantClient

from evals.retrieval_metrics import norm
from ledgerline.agents.context import AppContext
from ledgerline.agents.evidence import Evidence, EvidencePool
from ledgerline.agents.router import FULL_FEATURES, QAAgent
from ledgerline.agents.verifier import Draft, DraftSentence, verify
from ledgerline.core.llm import LLMParseError
from ledgerline.retrieval.store import ChunkStore

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evals" / "results"
REFUSAL = re.compile(
    r"insufficient evidence|not (?:in|available in) the (?:data room|evidence)|"
    r"cannot be determined|no information",
    re.I,
)


class StoreAdapter:
    def __init__(self, store: ChunkStore, mode: str) -> None:
        self.store = store
        self.mode = mode

    def search(self, q: str, k: int = 6, mode: str = "hybrid") -> Any:
        return self.store.search(q, k=k, mode=self.mode)  # type: ignore[arg-type]


CONFIGS: dict[str, dict[str, Any]] = {
    "L1_naive_rag": {"collection": "ll_naive", "mode": "dense", "features": frozenset()},
    "L2_hybrid": {"collection": "ll_hybrid_nohdr", "mode": "hybrid", "features": frozenset()},
    "L3_headers": {"collection": "ll_hybrid", "mode": "hybrid", "features": frozenset()},
    "L4_visual": {"collection": None, "features": frozenset({"router", "visual"})},
    "L5_graph": {"collection": None, "features": frozenset({"router", "visual", "graph"})},
    "L6_temporal": {
        "collection": None,
        "features": frozenset({"router", "visual", "graph", "temporal"}),
    },
    "L7_full": {"collection": None, "features": FULL_FEATURES},
}


class Judgement(BaseModel):
    label: Literal["correct", "partially_correct", "incorrect"]
    reason: str


JUDGE_SYSTEM = """You grade an AI system's answer against a reference answer written from the
source document. 'correct' = states the key facts of the reference (wording may differ, extra
correct detail is fine); 'partially_correct' = some key facts right, some missing or vague;
'incorrect' = wrong, contradicts the reference, or refuses when the reference has an answer."""


def load_items() -> tuple[list[dict[str, Any]], str]:
    g = ROOT / "evals" / "golden"
    for name, label in (
        ("approved.jsonl", "human-approved golden set"),
        ("candidates.jsonl", "LLM-generated candidates (pending human review)"),
    ):
        p = g / name
        if p.exists() and p.read_text().strip():
            return [json.loads(x) for x in p.read_text().splitlines() if x.strip()], label
    raise SystemExit("no golden items; run scripts/generate_golden.py")


def numbers(text: str) -> list[float]:
    out = []
    for m in re.finditer(r"-?\d[\d,]*(?:\.\d+)?", text):
        with contextlib.suppress(ValueError):
            out.append(float(m.group(0).replace(",", "")))
    return out


def numeric_ok(answer: str, value: float, tol: float) -> bool:
    for x in numbers(answer):
        for cand in (x, x / 100, x * 100):
            if abs(cand - value) <= max(tol, 1e-9) or (tol == 0 and round(cand) == round(value)):
                return True
    return False


def run_one(
    ctx: AppContext, cfg_name: str, item: dict[str, Any], client: QdrantClient
) -> dict[str, Any]:
    cfg = CONFIGS[cfg_name]
    store = (
        StoreAdapter(ChunkStore(client, cfg["collection"]), cfg["mode"])
        if cfg["collection"]
        else None
    )
    agent = QAAgent(ctx, f"eval-{cfg_name}", features=cfg["features"], store=store)
    q = str(item["question"])
    if item.get("as_of") and item["type"] == "temporal" and "as of" not in q.lower():
        q = f"As of {item['as_of']}, {q}"
    t0 = time.perf_counter()
    spend0 = ctx.llm.spend.run_spend(f"eval-{cfg_name}")
    try:
        out = agent.answer(q)
    except Exception as exc:
        return {
            "qid": item["qid"],
            "type": item["type"],
            "error": str(exc)[:200],
            "correct": 0.0,
            "latency_ms": (time.perf_counter() - t0) * 1000,
            "cost": 0.0,
        }
    kept = [s for s in out["sentences"] if s["status"] == "supported"]
    answer = " ".join(s["text"] for s in kept) if kept else out["answer"]
    refused = out["insufficient"] or bool(REFUSAL.search(answer)) or not kept
    return {
        "qid": item["qid"],
        "type": item["type"],
        "answer": answer,
        "refused": refused,
        "sentences": kept,
        "evidence": out["evidence"],
        "route": out["route"],
        "escalated": out["escalated"],
        "latency_ms": out["latency_ms"],
        "cost": ctx.llm.spend.run_spend(f"eval-{cfg_name}") - spend0,
    }


def score(
    ctx: AppContext, item: dict[str, Any], r: dict[str, Any], cfg_name: str
) -> dict[str, Any]:
    if "error" in r:
        return r
    t = item["type"]
    gold_docs = {g["doc_id"] for g in item.get("gold", []) if g.get("doc_id")}
    accept_docs = gold_docs | {x.split("::")[0] for x in item.get("excerpts", [])}
    if t == "unanswerable" or item.get("unanswerable"):
        r["correct"] = 1.0 if r["refused"] else 0.0
    elif item.get("numeric"):
        n = item["numeric"]
        r["correct"] = (
            1.0
            if (
                not r["refused"]
                and numeric_ok(r["answer"], float(n["value"]), float(n["tolerance"]))
            )
            else 0.0
        )
    elif t == "temporal" and item.get("source") == "template":
        gd = next(iter(gold_docs))
        ok = gd in r["answer"] or any(gd in c for s in r["sentences"] for c in s["cites"])
        r["correct"] = 1.0 if ok and not r["refused"] else 0.0
    elif r["refused"]:
        r["correct"] = 0.0
    else:
        try:
            res = ctx.llm.complete(
                run_id=f"eval-judge-{cfg_name}",
                stage="eval",
                name="judge_answer",
                system=JUDGE_SYSTEM,
                output_model=Judgement,
                max_tokens=1500,
                messages=[
                    {
                        "role": "user",
                        "content": f"Question: {item['question']}\n"
                        f"Reference answer: {item['answer']}\nSystem answer: {r['answer']}",
                    }
                ],
            )
            lab = res.parsed.label if res.parsed else "incorrect"
        except LLMParseError:
            lab = "incorrect"
        r["correct"] = {"correct": 1.0, "partially_correct": 0.5, "incorrect": 0.0}[lab]
    r["false_refusal"] = (
        1.0 if r["refused"] and t != "unanswerable" and not item.get("unanswerable") else 0.0
    )
    cited_docs = [
        c.split("#")[0].removeprefix("[doc:")
        for s in r["sentences"]
        for c in s["cites"]
        if c.startswith("[doc:")
    ]
    if accept_docs and cited_docs:
        r["citation_precision"] = sum(d in accept_docs for d in cited_docs) / len(cited_docs)
    anchors = [g for g in item.get("gold", []) if g.get("anchor")]
    if anchors:
        blob = " ".join(norm(e["text"]) for e in r["evidence"])
        r["retrieval_hit"] = 1.0 if any(norm(g["anchor"]) in blob for g in anchors) else 0.0
    # Independent hallucination check of the final answer against the retrieved evidence.
    if r["sentences"]:
        pool = EvidencePool()
        ev_map = {}
        for e in r["evidence"]:
            ne = pool.add(Evidence.model_validate(e))
            for c in ne.cites:
                ev_map.setdefault(c, ne.eid)
        draft = Draft(
            sentences=[
                DraftSentence(
                    text=s["text"],
                    evidence_ids=list(dict.fromkeys(ev_map[c] for c in s["cites"] if c in ev_map)),
                )
                for s in r["sentences"]
            ]
        )
        v = verify(ctx.llm, draft, pool, f"eval-judge-{cfg_name}", "eval")
        r["claims"] = v.stats["claims"]
        r["unsupported_claims"] = v.stats["claims"] - v.stats["supported"]
    return r


def aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    def mean(key: str, subset: list[dict[str, Any]] | None = None) -> float:
        vals = [float(r[key]) for r in (subset if subset is not None else rows) if key in r]
        return round(statistics.fmean(vals), 4) if vals else float("nan")

    lat = sorted(float(r["latency_ms"]) for r in rows)
    claims = sum(r.get("claims", 0) for r in rows)
    num = [r for r in rows if r["type"] in ("numeric", "visual")]
    tmp = [r for r in rows if r["type"] == "temporal"]
    una = [r for r in rows if r["type"] == "unanswerable"]
    ans = [r for r in rows if r["type"] != "unanswerable"]
    return {
        "n": float(len(rows)),
        "answer_correctness": mean("correct"),
        "numeric_accuracy": mean("correct", num),
        "temporal_correctness": mean("correct", tmp),
        "refusal_accuracy": mean("correct", una),
        "false_refusal_rate": mean("false_refusal", ans),
        "citation_precision": mean("citation_precision"),
        "retrieval_hit_rate": mean("retrieval_hit"),
        "hallucinated_claim_rate": round(
            sum(r.get("unsupported_claims", 0) for r in rows) / claims, 4
        )
        if claims
        else float("nan"),
        "latency_p50_ms": round(lat[len(lat) // 2], 1) if lat else float("nan"),
        "latency_p95_ms": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1)
        if lat
        else float("nan"),
        "cost_per_question_usd": round(statistics.fmean(r["cost"] for r in rows), 6),
        "errors": float(sum("error" in r for r in rows)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="*", default=list(CONFIGS))
    ap.add_argument("--per-type", type=int, default=8, help="stratified sample size per type")
    ap.add_argument("--full-config", default="L7_full", help="config run on ALL items")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument(
        "--use-cache",
        action="store_true",
        help="allow LLM response-cache hits (cheaper, but distorts cost/latency)",
    )
    args = ap.parse_args()
    items, label = load_items()
    rng = random.Random(13)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        by_type.setdefault(it["type"], []).append(it)
    sample = [
        x
        for t in sorted(by_type)
        for x in rng.sample(by_type[t], min(args.per_type, len(by_type[t])))
    ]
    ctx = AppContext()
    if not args.use_cache:
        # Honest cost/latency: every config pays for its own model calls (no cross-config
        # cache hits). Judging still goes through the same client, uncached.
        ctx.llm.cache = None
    client = QdrantClient(url=ctx.settings.qdrant_url)
    RES.mkdir(parents=True, exist_ok=True)
    ablation: dict[str, Any] = {
        "dataset": label,
        "sample_per_type": args.per_type,
        "sample_n": len(sample),
        "full_n": len(items),
        "configs": {},
    }
    for cfg in args.configs:
        todo = items if cfg == args.full_config else sample

        def work(it: dict[str, Any], cfg: str = cfg) -> dict[str, Any]:
            return score(ctx, it, run_one(ctx, cfg, it, client), cfg)

        t0 = time.time()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(work, todo))
        slim = [{k: v for k, v in r.items() if k not in ("evidence",)} for r in rows]
        (RES / f"qa_{cfg}.json").write_text(json.dumps(slim, indent=1, default=str))
        sample_ids = {x["qid"] for x in sample}
        ablation["configs"][cfg] = aggregate([r for r in rows if r["qid"] in sample_ids])
        if cfg == args.full_config:
            per_type = {t: aggregate([r for r in rows if r["type"] == t]) for t in sorted(by_type)}
            per_type["overall"] = aggregate(rows)
            (RES / "qa_summary.json").write_text(json.dumps(per_type, indent=1))
        print(f"{cfg:14} {ablation['configs'][cfg]} ({time.time() - t0:.0f}s)", flush=True)
    (RES / "qa_ablation.json").write_text(json.dumps(ablation, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
