# Ledgerline — Build Plan

> AI consulting copilot for fintech engagements. It runs an "AI readiness & compliance" engagement on a client data room and produces a consultant-grade deliverable. Every claim is traceable to a source document, a data query, or a named model assumption.

Status: **APPROVED 2026-11-16 with the "cheapest way" directive.** See §5 for the resulting cost profile.

---

## 0. Guiding rules

1. **Traceability.** Every sentence in a deliverable carries one of three citation types:
   - `doc:<doc_id>#p<page>|§<clause>` for a document passage
   - `q:<query_id>` for a logged, re-runnable SQL or PM4Py query
   - `a:<assumption_id>` for a key in `config/roi_assumptions.yaml`

   If the verifier cannot tie a claim to its citation, the claim is rewritten or flagged. When evidence is missing, the output says "insufficient evidence" instead of guessing.
2. **No fabricated metrics.** Every README number is copied by a script from `evals/report.md`, which is produced by an actual eval run. The README build step fails when a metric has no source.
3. **Answer-key isolation.** `dataroom/_answer_key.json` is visible only to `evals/`. Four controls enforce this:
   - Ingestion skips `_`-prefixed paths.
   - The API container does not mount the file.
   - A pytest check greps `src/` for any reference to it.
   - A runtime path guard in the file loader rejects it.
4. **Phase gate.** Before each commit: ruff, mypy (strict on `src/ledgerline/core`), and pytest must pass, coverage on core must be at least 80%, the eval subset must pass, and the README metrics must be regenerated.
5. **Pinned versions.** Before adding a library, I check its current docs and PyPI or npm release and pin an exact version. Lockfiles (`uv.lock`, `pnpm-lock.yaml`) are committed.

---

## 1. Key technology choices (to be pinned in Phase 0)

| Concern | Choice | Notes |
|---|---|---|
| Runtime | Python 3.12 via `uv` | The machine has 3.13. uv will install 3.12. |
| LLM (default, all roles) | Claude Haiku 5.5 (`claude-haiku-5-5`), Anthropic Python SDK | Cheapest current model ($0.10 / $0.50 per MTok under 100K-token prompts). Effort `low` by default, raised per stage only if evals show a need. |
| LLM (optional quality profile) | Claude Opus 5.5 (`claude-opus-5-5`) | Opt-in with `LEDGERLINE_MODEL_PROFILE=quality`. Never used by default, in CI, or in evals. |
| LLM judge (evals) | Haiku 5.5, through the Message Batches API (50% off) | Deterministic metrics are preferred wherever possible. |
| Orchestration | LangGraph | See risk R3 about the Anthropic tool-choice constraint. |
| Parsing | Docling | Layout-aware parsing with table structure. Unstructured is the fallback for DOCX edge cases only if Docling fails on them. |
| Dense + sparse embeddings | FastEmbed (local, CPU): a BGE-family dense model plus Qdrant BM25 sparse | No external embedding API. Deterministic and CI-friendly. |
| Reranker | Cross-encoder via FastEmbed (BGE reranker family) | Runs locally. |
| Visual retrieval | `colpali-engine` with a ColQwen-family checkpoint | Exact checkpoint chosen in Phase 5. The CPU fallback is a small ColSmol/ColPali-family model, or a "captioned page" mode. |
| Vector DB | Qdrant | Collections: `chunks_hybrid` (named dense and sparse vectors) and `pages_visual` (multivector, MaxSim). |
| Graph | Neo4j Community | Selective extraction only. |
| Process mining | PM4Py, with DuckDB as the read-only metrics store | |
| App DB | Postgres | Engagements, review queue, edit log, audit log, eval runs. |
| API | FastAPI with SSE | |
| UI | Next.js (App Router), Tailwind, React Flow for process maps, Recharts | |
| MCP | Official `mcp` Python SDK | stdio and streamable HTTP. |
| Observability | OpenTelemetry sent to self-hosted Langfuse | **Off by default** (compose profile `observability`). Spans go to a local JSONL exporter otherwise. |
| Export | `python-docx`, ReportLab (PDF), Markdown | ReportLab instead of WeasyPrint: pure Python, no system libraries, reproducible output. |

---

## 2. Repository layout

```
ledgerline/
├── PLAN.md  README.md  Makefile  docker-compose.yml  .env.example  pyproject.toml
├── config/                  # roi_assumptions.yaml, stage_tool_allowlist.yaml, models.yaml
├── dataroom/                # GENERATED (gitignored except README); _answer_key.json lives here
├── corpus/regulatory/       # GENERATED cache + manifest.json (lineage metadata)
├── scripts/                 # generate_dataroom.py, fetch_regulatory_corpus.py, review_golden.py, build_readme_metrics.py
├── src/ledgerline/
│   ├── core/                # mypy-strict: models (pydantic), citations, settings, audit, cost accounting
│   ├── ingest/              # parsing, chunking, contextual headers, injection scan, visual render/embed
│   ├── retrieval/           # hybrid, rerank, temporal filter, visual search, diff_versions, router
│   ├── graph/               # extraction (Requirement/Control), loaders, gap queries
│   ├── process/             # PM4Py mining, DuckDB views, process_metrics tool
│   ├── roi/                 # opportunity model, sensitivity
│   ├── agents/              # LangGraph graph, stages, tools, verifier, drafting
│   ├── deliverables/        # memo, findings register, roadmap, ROI summary, exporters
│   ├── review/              # review queue + edit log
│   ├── guardrails/          # prompt-injection detector, PII scrubber, allow-lists
│   ├── api/                 # FastAPI app, SSE
│   └── mcp_server/
├── ui/                      # Next.js app
├── evals/                   # harness, golden set, answer-key scorer, ablations, report.md, charts/
├── tests/                   # unit + integration (testcontainers where needed)
└── docs/                    # ARCHITECTURE.md, DECISIONS.md, demo.gif, sample_memo.md
```

---

## 3. Phases

Each phase ends with tests, the eval subset (once it exists), a README metrics refresh, and a commit. Phases 1, 2, and 6 have no dependencies on each other.

### Phase 0: Scaffold
- `git init`, uv project, ruff/mypy/pytest config, pre-commit, and `.env.example` loaded with pydantic-settings.
- `docker-compose.yml` with Qdrant, Neo4j, Postgres, the API, and the UI. Langfuse goes under a `observability` profile with health checks.
- `core/`: the `Citation` union type, `AuditEvent` (step, tool, model, tokens in/out, cost, latency), the Anthropic client wrapper (cost metering, retries, refusal-fallback, PII-scrubbed logging), and the model profiles.
- GitHub Actions skeleton covering lint, typecheck, and tests.

**Acceptance criteria:**
- `docker compose up` brings every service to healthy.
- `make test` passes.
- CI passes on an empty PR.
- One smoke call through the client wrapper writes an audit row.

### Phase 1: Synthetic NovaPay data room and answer key
- `scripts/generate_dataroom.py` is seeded and deterministic (`--seed`). Every artifact is watermarked "SYNTHETIC — NovaPay is fictional".
- **Documents (about 40):** generated as MD, then rendered to DOCX (python-docx) and PDF (WeasyPrint/ReportLab). They cover:
  - SOPs: KYC, disputes, reconciliation, stablecoin reserves
  - Policies: AML/BSA, vendor risk, AI usage, data retention
  - The org chart
  - 5–6 vendor contracts with SLAs and risky clauses (auto-renewal, unlimited data reuse, no audit rights)
  - Board deck excerpts: matplotlib charts and tables on PDF pages, with some numbers available only in the charts
  - 4 incident postmortems
- **Event logs (about 200K events):** produced by simulated case generators per process (KYC, disputes/chargebacks, reconciliation). The simulation includes:
  - Rework loops
  - Manual handoffs
  - SLA breaches
  - Two or three named analysts who cause a bottleneck
  - A reconciliation manual-step share of about 40%

  Output is CSV and Parquet.
- **Tickets:** 5K, with categories, handle times, and channel.
- **Internal consistency:** a single `NovaPayWorld` config object drives every artifact (headcount, roles, vendors, volumes). Example: the org chart's analysts are the resources that appear in the logs, and the board deck volumes match the log totals.
- **Prompt-injection document:** one malicious document is seeded (a vendor "addendum" with hidden instructions in white text and in metadata).
- **`_answer_key.json`:** about 15–25 seeded gaps and inefficiencies. Each entry has an id, type, severity, the expected evidence location, the requirement it maps to, and the metric value where one applies.

**Acceptance criteria:**
- Generation is idempotent: the same seed produces the same SHA-256 manifest.
- Consistency tests pass. Example: the measured reconciliation manual share in the generated logs falls within 40% ± 2pp.
- No app module imports or opens the answer key (enforced by test).

### Phase 2: Regulatory corpus fetcher
- `scripts/fetch_regulatory_corpus.py` is idempotent. It keeps an HTTP cache with ETags and checksums, logs failures to `corpus/regulatory/fetch_log.jsonl`, and supports `--slice small|full`.
- **Sources** (current status checked on 2026-11-16; URLs are re-verified at build time):
  - **GENIUS Act** statute text (congress.gov / govinfo).
  - **OCC GENIUS Act rule.** The proposed rule (FR 2026-03-02, doc 2026-04089) is superseded by the final rule (FR 2026-10-23, doc 2026-21706), which takes effect 2027-01-18. This is the main temporal and diff demo.
  - **FDIC proposed rule** (FR 2026-04-10) and **Treasury proposed rules** (state-regime principles, FR 2026-04-03; issuance, offer, and sale, FR 2026-08-18). I will check whether any of these have been finalized before hardcoding.
  - **FinCEN AML/CFT program rule.** The 2024-07-03 NPRM is withdrawn and superseded by the 2026-04-10 NPRM (FR doc 2026-07033). This is a second lineage example. I will also check whether a final rule exists.
  - **CFPB:** Reg E error resolution (12 CFR 1005.11) and Reg Z billing disputes (1026.13), from eCFR with point-in-time versions.
  - **NIST AI RMF 1.0** and the **Generative AI profile (NIST AI 600-1)**.
  - **EU AI Act** (Regulation (EU) 2024/1689) from EUR-Lex.
- Federal Register content is pulled through its JSON API. eCFR content uses its versioner API, which provides `as_of` dates.
- The `manifest.json` schema per document: `doc_id, issuer, doc_type, title, pub_date, effective_date, valid_from, valid_to, supersedes[], superseded_by, source_url, sha256, retrieved_at`.

**Acceptance criteria:**
- A second run makes zero network calls (cache hit).
- The lineage graph in the manifest validates: there are no cycles, and every superseded document has a `valid_to`.
- The small slice fetches in under 2 minutes.

### Phase 3: Text ingestion, guardrail scan, and eval harness v0
- **Parsing:** Docling turns documents into a structured tree.
- **Chunking:**
  - Regulations are split by section/§/clause.
  - SOPs and policies are split by heading.
  - Contracts are split by clause number.
  - Tables are kept whole and also serialized to Markdown.
- **Contextual header** prepended to every chunk before embedding: `[title | issuer | section path | version | effective date]`.
- **Prompt-injection detection at ingest.** A heuristic and a classifier flag documents with hidden text, instruction-like imperatives aimed at an AI, or metadata payloads. Flagged chunks are quarantined: they stay retrievable as evidence but are marked as untrusted data and never treated as instructions.
- **Qdrant:** a hybrid collection with dense and BM25 vectors, fused with RRF, then reranked.
- **Eval harness v0:**
  - Retrieval metrics: recall@k, MRR, nDCG.
  - LLM-generated golden-candidate pipeline, plus `scripts/review_golden.py`, a TUI where you approve, edit, or reject each item.
  - A **naive RAG baseline** (fixed-size chunks, dense only) is recorded as the first ablation row.

**Acceptance criteria:**
- The malicious document is flagged with 100% detection on the seeded doc, and the false-positive rate on the rest of the data room is reported.
- Hybrid with rerank beats the naive baseline on recall@10 for the reviewed golden subset, using real numbers recorded in `evals/report.md`.
- 200+ golden candidates are generated across the 6 types, ready for your review. **Blocking dependency: your review time.**

### Phase 4: Temporal retrieval and `diff_versions`
- Every regulatory chunk carries `valid_from`, `valid_to`, `version_id`, and `lineage_id`. Qdrant payload filters apply `valid_from <= as_of < valid_to`.
- **Default policy:** return the version that governs on `as_of`. If a later version exists that is adopted but not yet effective, it is surfaced as "upcoming". Example: on 2026-11-16 the OCC final rule is adopted but its effective date is 2027-01-18.
- `diff_versions(lineage_id, from, to)` aligns sections between versions by heading and embedding similarity. It produces a clause-level diff (added, removed, modified) and an LLM summary of each change, with citations to both versions.

**Acceptance criteria:**
- Temporal correctness of at least the target threshold on the temporal golden subset. The threshold is set after the first measured run.
- The OCC proposed-to-final diff renders with citations to both versions.

### Phase 5: Visual retrieval path
- Pages are rendered to PNG with pypdfium2 and stored for the UI's citation viewer.
- Only table- and chart-heavy pages are embedded with ColQwen: board decks and rule tables, detected by Docling layout stats. Visual search uses multivector late interaction in Qdrant.
- **CPU fallback,** documented in `DECISIONS.md`: a smaller ColPali-family checkpoint, or Claude vision captions of the page indexed as text. Both are measurable in the ablation.

**Acceptance criteria:**
- The table/visual golden subset shows a measured lift over the text-only path.
- Indexing the demo data room fits within a documented CPU time budget on an M-series Mac.

### Phase 6: Process mining
- PM4Py runs on the event logs: inductive-miner process maps, variants, cycle time, rework rate, handoff counts, resource bottlenecks, and SLA breach rate.
- DuckDB views are opened through a **read-only** connection. `process_metrics(process, metric, filters)` is a tool that runs whitelisted parameterized SQL only. Every call is logged with a `query_id`, and its SQL and result hash are stored so the call can be re-run.

**Acceptance criteria:**
- Mined metrics match the generator's ground-truth parameters within tolerance. These are unit tests against the `NovaPayWorld` config, not the answer key.
- Attempts to write through the tool fail.

### Phase 7: ROI and opportunity model
- `config/roi_assumptions.yaml` holds every assumption with an id, low/base/high values, units, and rationale. Examples: loaded hourly cost, automation rate by task type, implementation cost bands, and regulatory sensitivity multipliers.
- Each opportunity is scored on four inputs:
  - Hours saved, taken from `process_metrics` outputs, which carry their `q:` citations
  - Implementation cost
  - Risk and regulatory sensitivity
  - Time to value

  The output includes NPV/payback plus a tornado-style sensitivity across the low/base/high cases.
- The model is pure, deterministic Python. The LLM never computes numbers; it only calls `roi_model` and `calculator`.

**Acceptance criteria:**
- Property-based tests (hypothesis) check monotonicity, for example that more hours saved never decreases value.
- Every output number traces back to an assumption id or a query id.

### Phase 8: Knowledge graph and gap analysis
- **Selective extraction** with an LLM and structured outputs:
  - Requirement nodes come only from obligation-bearing clauses ("shall", "must", "required"), pre-filtered by a classifier.
  - Control nodes come only from policies and SOPs.
- **Graph model:** Process, Control, Requirement, Vendor, and Role nodes, with edges Process→Control→Requirement, Vendor→Process, and Role→Process. Every node and edge stores `source_doc`, `page` or `clause`, `extraction_model`, and `confidence`.
- **Gap analysis** has two parts:
  1. A Cypher query finds Requirements that no Control satisfies.
  2. For partial matches, an LLM judges coverage, citing evidence on both sides, and returns a status of covered, partial, or missing, plus a severity.

**Acceptance criteria:**
- Measured answer-key precision and recall for seeded compliance gaps, reported per run.
- Every graph element carries provenance (enforced by test).

### Phase 9: Agentic orchestration, router, and verifier
- **LangGraph stage machine:** Discovery → Process Analysis → Opportunity Sizing → Gap Analysis → Synthesis. A planner breaks each stage into sub-questions.
- **Per-stage tool allow-lists** live in `config/stage_tool_allowlist.yaml` and are enforced in code, not only in the prompt.
- **Adaptive router:** each sub-question first goes through cheap hybrid search. A self-check (evidence sufficiency: coverage, citations present, temporal match) escalates to graph, visual, or multi-hop agentic retrieval. Every routing decision is logged.
- **Verifier pass:** claims are split into atomic sentences.
  - Each sentence is checked against its cited evidence (NLI-style LLM judgment).
  - Each number is re-derived by re-running its `q:` query or `a:` assumption.
  - Unsupported claims are rewritten or flagged, and "insufficient evidence" is emitted when nothing supports them.

**Acceptance criteria:**
- One full engagement runs end to end on the dev model.
- Every sentence in the draft has a citation, and citation coverage is 100% by construction (enforced by schema).
- The verifier catches seeded unsupported claims in a unit fixture.

### Phase 10: Deliverables, human-in-the-loop review, and audit
- Four deliverables: an executive memo (2 pages), a findings register, a 90-day roadmap (quick wins vs. strategic bets), and an ROI summary with an assumptions appendix. They export to DOCX, PDF, and MD with a "Not legal advice" disclaimer, and citations render as footnotes or links.
- **Review queue** in Postgres: accept, edit, or reject each finding. Edits are stored as diffs with reviewer, timestamp, and reason. Re-export reflects decisions.
- **Audit log:** every agent step, tool call, model, token count, cost, and latency. PII is scrubbed before write.

**Acceptance criteria:**
- Exports open cleanly (validated with python-docx and pypdf).
- The review round trip is covered by tests.
- Audit totals match the provider usage fields.

### Phase 11: API and UI
- **FastAPI:** engagements CRUD, `POST /engagements/{id}/run` with an SSE trace stream, plus search, diff, review, and eval endpoints.
- **Next.js screens:**
  - Engagement overview
  - Live agent trace (stage → tool calls → evidence)
  - Process map viewer (variants, bottlenecks)
  - Opportunity matrix (value vs. effort)
  - Gap register with clickable citations that open the page image with the passage highlighted
  - Regulation version diff
  - Review queue
  - Eval dashboard

**Acceptance criteria:**
- A Playwright smoke test exercises every screen against a recorded engagement.
- A full engagement can be run from the UI.

### Phase 12: MCP server
- Tools: `run_engagement`, `ask_dataroom`, `gap_check`, `size_opportunity`, `diff_regulation`. They reuse the same service layer and allow-lists.
- Config snippets are provided for Claude Desktop and Claude Code.

**Acceptance criteria:**
- An MCP Inspector or SDK client test calls each tool.
- Documentation lets someone connect from Claude Code in one step.

### Phase 13: Full evals, ablations, and report
- **Answer-key scoring:** precision and recall of seeded gaps and inefficiencies, plus severity agreement (weighted kappa).
- **Golden Q&A metrics** per route and per question type:
  - recall@k, MRR, nDCG
  - answer correctness, faithfulness, citation precision
  - numeric accuracy, temporal correctness, refusal accuracy
  - hallucinated-claim rate
  - p50/p95 latency and cost per engagement
- **Ablation ladder:** naive → hybrid+rerank → +contextual headers → +visual → +graph → +temporal → full agentic with verifier.
- `evals/report.md` is generated with charts. `scripts/build_readme_metrics.py` copies its numbers into the README.
- **CI fast subset** runs on every PR:
  - Deterministic retrieval metrics on a fixed slice, with no API key required. Local embeddings make this reproducible.
  - When the `ANTHROPIC_API_KEY` secret is present, an LLM subset of about 30 items on the dev model.
  - The job fails on a regression larger than a tolerance relative to the committed baseline.

**Acceptance criteria:** The report is regenerated from a clean run, and README numbers match it exactly (enforced by a CI check).

### Phase 14: Hardening, docs, and demo
- Observability: OTel spans for each stage, tool, and LLM call are sent to Langfuse.
- PII scrubbing is in place for all logs.
- Read-only DB roles for DuckDB and Postgres reporting, plus a read-only Neo4j user for the graph tool.
- Docs:
  - `docs/ARCHITECTURE.md` with Mermaid diagrams
  - `docs/DECISIONS.md` with ADRs on temporal retrieval, selective graph extraction, ColPali, ROI assumptions, and the router
  - The README: a 5-minute quickstart, a demo GIF, a sample memo, and the ablation table
- `make demo` does the whole run: generate → fetch small slice → ingest → run one engagement → export.

**Acceptance criteria:**
- `make demo` succeeds from a fresh clone with only `ANTHROPIC_API_KEY` set.
- Every README metric links back to the report.

---

## 4. Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Local compute.** ColQwen (multi-billion parameter) is slow on CPU, and the full Docker stack (Neo4j, Qdrant, Langfuse with ClickHouse) is RAM-heavy on a laptop. | Visual embedding runs on selected pages only and is cached. The CPU fallback is documented. Langfuse is an optional compose profile. A target RAM budget is documented. |
| R2 | **Golden-set review is a bottleneck.** 200+ items need your approval. | Phase 3 produces candidates early. Review runs in parallel with Phases 4–8. The CI subset only needs about 60 reviewed items to start. |
| R3 | **Current-model API constraints** (Haiku 5.5 / Opus 5.5). Forced `tool_choice` (`any`/`tool`) returns a 400, and thinking cannot be disabled. Some LangChain helpers, such as `with_structured_output`, force tool choice. | Use native structured outputs (`output_config.format`) and `tool_choice: auto` with strict tools. Wrap the Anthropic SDK directly inside LangGraph nodes instead of using `langchain-anthropic` chat-model helpers. A contract test runs against both model profiles. |
| R4 | **LLM-judge bias and self-grading.** | Use deterministic metrics where possible (retrieval, numeric, temporal, refusal). Judge prompts are versioned. A spot-check sample is human-labelled to report judge agreement. |
| R5 | **Langfuse self-hosting complexity.** v3 needs Postgres, ClickHouse, Redis, and object storage. | Keep it behind a profile with pinned images. OTel export still works to a console or file exporter when it is off. |
| R6 | **Regulatory sources change or block bots.** EUR-Lex and some agency sites rate-limit. | Federal Register and eCFR APIs come first. The fetcher caches, backs off, sets a generic User-Agent, and logs failures. A checked-in small-slice snapshot with checksums is used only if the licensing permits it, since these are public-domain US documents. |
| R7 | **Regulatory status drift.** Rules get finalized after the build. | Lineage lives in data (`manifest.json`), not code. Re-running the fetcher updates versions. The temporal tests use fixed `as_of` dates. |
| R8 | **Answer-key leakage** through prompts, few-shot examples, or tuning. | The isolation controls in §0.3 apply. Golden-set and answer-key authoring are kept separate from the prompts. Prompts are frozen before final eval runs, and the frozen hash is recorded in the report. |
| R9 | **Cost.** | Haiku 5.5 by default, plus a response cache, the Batches API, and local embeddings. Hard per-run and per-day USD caps are enforced in the client (see §5). |
| R10 | **Scope.** This is a large build. | The phases are independently demoable. If time runs short, cut UI polish and the EU AI Act depth before evals or traceability. |
| R11 | **Legal and ethical framing.** | "Not legal advice" disclaimer on all deliverables, SYNTHETIC labels on all client data, and no real company names in the client world. |

---

## 5. Cost profile (decided: "cheapest way")

These decisions replace the earlier open questions.

| Question | Decision |
|---|---|
| Q1 Models | **Haiku 5.5 everywhere by default.** Opus 5.5 is available only as an opt-in `quality` profile. |
| Q2 Eval judge | Haiku 5.5, run through the Batches API at 50% off. Deterministic metrics come first. Judge agreement is reported against a small human-labelled sample. |
| Q3 Budget | A hard spend cap enforced in the LLM client: `LEDGERLINE_MAX_USD_PER_RUN` (default $1.00) and `LEDGERLINE_MAX_USD_PER_DAY` (default $5.00). A run that would exceed the cap stops with an error. |
| Q4 Hardware | Assume CPU only (Apple Silicon). The visual path uses the smallest ColPali-family checkpoint on selected pages only, with no LLM page captioning by default. |
| Q5 GitHub | Local git only. The CI workflow is written but needs no API key: the PR gate runs deterministic metrics only. |
| Q6 EU AI Act | Ingest the full text. Graph extraction is limited to the relevant articles. |

**Other cost levers:**
- All embeddings, BM25, and reranking run locally (FastEmbed), at $0.
- Stable system and tool prefixes use prompt caching.
- An LLM response cache keyed on (model, prompt hash) makes repeated eval runs and `make demo` reruns nearly free.
- Selective graph extraction: a regex/classifier pre-filter means only obligation-bearing clauses reach the LLM.
- Golden candidates are generated once with the Batches API and then cached.
- The heavy services are opt-in compose profiles: Langfuse, and the UI dev server in non-demo runs.
- The demo uses the `small` regulatory slice.
