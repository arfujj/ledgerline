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
        "precision, numeric accuracy, temporal correctness, refusal accuracy, "
        "hallucinated-claim rate, answer-key precision/recall, cost per engagement.",
        "",
    ]
    (HERE / "report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
