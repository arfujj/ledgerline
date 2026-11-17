"""Build evals/report.md (+ charts) from evals/results/*.json. Only reports what was measured."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
RES = HERE / "results"
LABELS = {
    "naive_dense": "Naive RAG (fixed chunks, dense)",
    "hybrid_nohdr": "Hybrid (structure chunks, dense+BM25)",
    "hybrid_nohdr_rerank": "Hybrid + rerank",
    "hybrid_hdr": "Hybrid + contextual headers",
    "hybrid_hdr_rerank": "Hybrid + rerank + contextual headers",
}


def _git() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def retrieval_table(summary: dict[str, dict[str, object]]) -> list[str]:
    rows = [
        "| Configuration | n | Recall@5 | Recall@10 | MRR | nDCG@10 | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name in LABELS:
        if name not in summary:
            continue
        s = summary[name]
        lat = s["latency_ms"]
        rows.append(
            f"| {LABELS[name]} | {s['n']} | {s['recall@5']:.3f} | {s['recall@10']:.3f} | "
            f"{s['mrr']:.3f} | {s['ndcg@10']:.3f} | {lat['p50']} | {lat['p95']} |"
        )  # type: ignore[index]
    return rows


def observations(summary: dict[str, dict[str, object]]) -> list[str]:
    """Computed comparisons only; no hand-entered numbers."""

    def d(a: str, b: str, m: str) -> str | None:
        if a in summary and b in summary:
            return f"{float(summary[b][m]) - float(summary[a][m]):+.3f}"  # type: ignore[arg-type]
        return None

    out = ["Computed deltas:", ""]
    for a, b, label in (
        ("naive_dense", "hybrid_nohdr", "structure-aware chunks + BM25 vs naive"),
        ("hybrid_nohdr", "hybrid_hdr", "adding contextual headers"),
        ("hybrid_hdr", "hybrid_hdr_rerank", "adding the cross-encoder reranker"),
    ):
        r, m = d(a, b, "recall@10"), d(a, b, "mrr")
        if r is not None:
            out.append(f"- {label}: Recall@10 {r}, MRR {m}")
    return out


def chart(summary: dict[str, dict[str, object]], path: Path) -> None:
    names = [n for n in LABELS if n in summary]
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=120)
    x = range(len(names))
    for off, metric, color in ((-0.2, "recall@10", "#4C78A8"), (0.2, "mrr", "#F58518")):
        ax.bar(
            [i + off for i in x],
            [float(summary[n][metric]) for n in names],
            0.4,  # type: ignore[arg-type]
            label=metric,
            color=color,
        )
    ax.set_xticks(
        list(x), [LABELS[n].replace(" (", "\n(").replace(" + ", "\n+ ") for n in names], fontsize=7
    )
    ax.set_ylim(0, 1)
    ax.legend(fontsize=8)
    ax.set_title("Retrieval ablation (seed set)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, metadata={"Software": None})
    plt.close(fig)


def main() -> None:
    lines = [
        "# Ledgerline evaluation report",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC from commit `{_git()}` by "
        "`evals/report.py`. Every number below is read from `evals/results/*.json`, "
        "produced by actually running the evals. Nothing is hand-entered.",
        "",
    ]
    summary_path = RES / "retrieval_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        (HERE / "charts").mkdir(exist_ok=True)
        chart(summary, HERE / "charts" / "retrieval_ablation.png")
        best = max(summary, key=lambda n: summary[n]["mrr"])
        detail = json.loads((RES / f"retrieval_{best}.json").read_text())
        lines += [
            "## Retrieval ablation",
            "",
            "Dataset: **seed retrieval set v0**, made up of author-written questions "
            "(`evals/data/seed_retrieval.jsonl`) "
            "over the data room and regulatory corpus. Gold sources are a document plus a "
            "verbatim anchor span, so every chunking strategy is scored the same way. "
            "Retrieval is local (FastEmbed), so these runs cost $0.",
            "",
            *retrieval_table(summary),
            "",
            "![Retrieval ablation](charts/retrieval_ablation.png)",
            "",
            f"Per-type results for the best configuration (**{LABELS[best]}**):",
            "",
            "| Type | Recall@5 | Recall@10 | MRR | nDCG@10 |",
            "|---|---|---|---|---|",
        ]
        for t, m in detail["by_type"].items():
            lines.append(
                f"| {t} | {m['recall@5']:.3f} | {m['recall@10']:.3f} | {m['mrr']:.3f} | "
                f"{m['ndcg@10']:.3f} |"
            )
        lines.append("")
    qa = RES / "qa_ablation.json"
    if qa.exists():
        a = json.loads(qa.read_text())
        labels = {
            "L1_naive_rag": "L1 Naive RAG (fixed chunks, dense)",
            "L2_hybrid": "L2 Hybrid (structure chunks, dense+BM25)",
            "L3_headers": "L3 + contextual headers",
            "L4_visual": "L4 + visual (ColPali + page reading)",
            "L5_graph": "L5 + knowledge graph",
            "L6_temporal": "L6 + temporal (as-of)",
            "L7_full": "L7 Full: agentic escalation + verifier",
        }
        cols = [
            ("answer_correctness", "Correct"),
            ("numeric_accuracy", "Numeric"),
            ("temporal_correctness", "Temporal"),
            ("refusal_accuracy", "Refusal"),
            ("false_refusal_rate", "False refusal"),
            ("citation_precision", "Cite prec."),
            ("hallucinated_claim_rate", "Halluc. claims"),
            ("latency_p50_ms", "p50 ms"),
            ("latency_p95_ms", "p95 ms"),
            ("cost_per_question_usd", "$/question"),
        ]
        lines += [
            "## Answer-level ablation",
            "",
            f"Dataset: **{a['dataset']}**. Stratified sample of {a['sample_per_type']} "
            f"items per question type (n={a['sample_n']}), identical across configs. "
            "Model: Claude Haiku 5.5 for every role. Answer correctness is deterministic "
            "for numeric, visual, template-temporal and unanswerable items, and graded by "
            "a Claude Haiku judge against the reference answer for the rest. The "
            "hallucinated-claim rate comes from the same independent post-hoc entailment "
            "check for every config.",
            "",
            "| Config | " + " | ".join(c[1] for c in cols) + " |",
            "|---|" + "---|" * len(cols),
        ]

        def fmt(k: str, v: float) -> str:
            if v != v:  # NaN
                return "-"
            if k.startswith("latency"):
                return f"{v:,.0f}"
            if k.startswith("cost"):
                return f"{v:.5f}"
            return f"{v:.3f}"

        for k, label in labels.items():
            if k in a["configs"]:
                m = a["configs"][k]
                lines.append(f"| {label} | " + " | ".join(fmt(c, m[c]) for c, _ in cols) + " |")
        lines.append("")
        qs = RES / "qa_summary.json"
        if qs.exists():
            t = json.loads(qs.read_text())
            lines += [
                f"Full system (L7) on **all {a['full_n']} items**, by question type:",
                "",
                "| Type | n | Correct | Cite prec. | Retrieval hit | Halluc. claims | "
                "p50 ms | $/question |",
                "|---|---|---|---|---|---|---|---|",
            ]
            for typ, m in t.items():
                lines.append(
                    f"| {typ} | {int(m['n'])} | {fmt('a', m['answer_correctness'])} | "
                    f"{fmt('a', m['citation_precision'])} | "
                    f"{fmt('a', m['retrieval_hit_rate'])} | "
                    f"{fmt('a', m['hallucinated_claim_rate'])} | "
                    f"{fmt('latency', m['latency_p50_ms'])} | "
                    f"{fmt('cost', m['cost_per_question_usd'])} |"
                )
            lines.append("")
    eng_root = HERE.parent / "data" / "engagement"
    latest = eng_root / "LATEST"
    if latest.exists():
        e = json.loads((eng_root / latest.read_text().strip() / "engagement.json").read_text())
        memo_claims = sum(sec["verifier"]["claims"] for sec in e.get("memo", []))
        memo_ok = sum(sec["verifier"]["supported"] for sec in e.get("memo", []))
        lines += [
            "## Cost and latency per engagement",
            "",
            "| Run | Model | Cost (USD) | Wall time (s) | Memo claims verified | Findings |",
            "|---|---|---|---|---|---|",
            f"| {e['run_id']} | {e.get('model')} via {e.get('provider')} | "
            f"{e['cost_usd']:.4f} | {e['latency_s']} | {memo_ok:.0f}/{memo_claims:.0f} | "
            f"{len(e['gaps']) + len(e['inefficiencies']) + len(e['security'])} |",
            "",
        ]
    tp = RES / "temporal.json"
    if tp.exists():
        t = json.loads(tp.read_text())["summary"]
        lines += [
            "## Temporal (as-of) correctness",
            "",
            "As-of questions over versioned rulemakings (OCC GENIUS Act issuer rule "
            "proposed→final; FinCEN AML/CFT program NPRM 2024→2026). An item is correct "
            "when the top retrieved chunk from that lineage comes from the version that "
            "governed on the as-of date. Items are built from the corpus manifest by a "
            "template.",
            "",
            "| Retrieval | n | Temporal correctness |",
            "|---|---|---|",
        ]
        for mode, label in (
            ("no_filter", "Hybrid, no version filter"),
            ("as_of_filter", "Hybrid + as-of version filter"),
        ):
            if mode in t:
                lines.append(
                    f"| {label} | {t[mode]['n']} | {t[mode]['temporal_correctness']:.3f} |"
                )
        lines.append("")
    ak = RES / "answer_key.json"
    if ak.exists():
        a = json.loads(ak.read_text())
        labels = {
            "gaps_all": "Graph gap analysis: all findings",
            "gaps_conf_ge_0.6": "Graph gap analysis: confidence >= 0.6",
            "engagement_gaps": "Full engagement: compliance gaps",
            "engagement_inefficiencies": "Full engagement: inefficiencies",
        }
        lines += [
            "## Answer-key scoring (seeded gaps and inefficiencies)",
            "",
            "Findings are matched to the eval-only answer key with a deterministic rule: "
            "the finding must cite one of the item's evidence documents and mention a "
            "distinctive keyword. Precision counts real but *unseeded* findings as "
            "false positives, so it is a lower bound. Unmatched findings are listed in "
            "`evals/results/answer_key.json` for human review.",
            "",
            "| Run | Findings | Precision | Recall | Severity exact | Severity ±1 | Missed |",
            "|---|---|---|---|---|---|---|",
        ]
        for k, label in labels.items():
            if k in a:
                v = a[k]
                lines.append(
                    f"| {label} | {v['findings']} | {v['precision']:.3f} | "
                    f"{v['recall']:.3f} | {v['severity_exact']:.3f} | "
                    f"{v['severity_within_one']:.3f} | {', '.join(v['missed']) or '-'} |"
                )
        lines.append("")
    g = RES / "guardrails.json"
    if g.exists():
        gr = json.loads(g.read_text())
        lines += [
            "## Guardrails: prompt-injection detection at ingest",
            "",
            "| Seeded injection docs | Detected | Detection recall | False positives | "
            "Clean docs scanned |",
            "|---|---|---|---|---|",
            f"| {len(gr['seeded'])} | {len(set(gr['seeded']) & set(gr['quarantined']))} | "
            f"{gr['detection_recall']:.2f} | {len(gr['false_positives'])} | "
            f"{gr['clean_docs']} |",
            "",
        ]
    lines += [
        "## Not yet measured",
        "",
        "These metrics require later phases or an approved golden set, and are deliberately "
        "left blank rather than estimated: answer correctness, faithfulness, citation "
        "precision, numeric accuracy, refusal accuracy, "
        "hallucinated-claim rate, cost per engagement.",
        "",
    ]
    (HERE / "report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
