# Ledgerline

> AI consulting copilot for fintech engagements. It runs an "AI readiness & compliance" engagement on a client data room and produces a consultant-grade deliverable. Every claim is traceable to a source document, a data query, or an explicit model assumption.

**Status:** under construction. See [PLAN.md](PLAN.md) for the phases. Metrics appear here only after `evals/report.md` has been produced by a real eval run.

All client data is **SYNTHETIC**. NovaPay is a fictional company. Outputs are **not legal advice**.

## Quickstart (Phase 0)

```bash
cp .env.example .env      # add ANTHROPIC_API_KEY
uv sync
make check                # lint + mypy (strict on core) + tests with coverage
make up                   # Qdrant, Neo4j, Postgres, API  →  http://localhost:8000/health
make smoke                # one Claude Haiku 5.5 call through the audited client (fractions of a cent)
```

**Cost defaults:** Claude Haiku 5.5 is used everywhere, with an on-disk response cache. Hard caps are $1 per run and $5 per day, both configurable in `.env`.

## Measured results

<!-- METRICS:START -->
_Copied verbatim from [evals/report.md](evals/report.md) (Generated 2026-11-16 22:09 UTC from commit `af3bc81`)._

## Retrieval ablation

Dataset: **seed retrieval set v0**, made up of author-written questions (`evals/data/seed_retrieval.jsonl`) over the data room and regulatory corpus. Gold sources are a document plus a verbatim anchor span, so every chunking strategy is scored the same way. Retrieval is local (FastEmbed), so these runs cost $0.

| Configuration | n | Recall@5 | Recall@10 | MRR | nDCG@10 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| Naive RAG (fixed chunks, dense) | 40 | 0.675 | 0.700 | 0.623 | 0.642 | 7.7 | 23.8 |
| Hybrid (structure chunks, dense+BM25) | 40 | 0.725 | 0.825 | 0.589 | 0.645 | 7.8 | 10.3 |
| Hybrid + rerank | 40 | 0.775 | 0.800 | 0.705 | 0.728 | 2188.6 | 3640.4 |
| Hybrid + contextual headers | 40 | 0.875 | 0.900 | 0.699 | 0.750 | 10.7 | 34.1 |
| Hybrid + rerank + contextual headers | 40 | 0.800 | 0.800 | 0.746 | 0.760 | 2172.4 | 2776.4 |

![Retrieval ablation](evals/charts/retrieval_ablation.png)

Per-type results for the best configuration (**Hybrid + rerank + contextual headers**):

| Type | Recall@5 | Recall@10 | MRR | nDCG@10 |
|---|---|---|---|---|
| fact | 0.870 | 0.870 | 0.819 | 0.832 |
| regulatory | 0.583 | 0.583 | 0.542 | 0.553 |
| table | 1.000 | 1.000 | 0.900 | 0.926 |
## Temporal (as-of) correctness

As-of questions over versioned rulemakings (OCC GENIUS Act issuer rule proposed→final; FinCEN AML/CFT program NPRM 2024→2026). An item is correct when the top retrieved chunk from that lineage comes from the version that governed on the as-of date. Items are built from the corpus manifest by a template.

| Retrieval | n | Temporal correctness |
|---|---|---|
| Hybrid, no version filter | 38 | 0.500 |
| Hybrid + as-of version filter | 38 | 1.000 |
## Guardrails: prompt-injection detection at ingest

| Seeded injection docs | Detected | Detection recall | False positives | Clean docs scanned |
|---|---|---|---|---|
| 1 | 1 | 1.00 | 0 | 55 |
<!-- METRICS:END -->
