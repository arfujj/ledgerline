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
