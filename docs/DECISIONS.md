# Architecture Decision Records

Each ADR records the context, the decision, and its consequences. ADRs are added as phases land.

## ADR-001: Cheapest-cost operating profile

**Context.** The owner asked for the build to run "the cheapest way".

**Decision.** The defaults are chosen to minimise spend:
- **Model.** Claude Haiku 5.5 handles every LLM role by default. Opus 5.5 is available only as an opt-in `quality` profile.
- **Retrieval.** Embeddings, BM25 and reranking all run locally with FastEmbed, so retrieval costs nothing.
- **Caching.** An on-disk LLM response cache and an embedding cache are on by default.
- **Batch work.** Golden-set generation and LLM judging go through the Message Batches API, which is 50% cheaper.
- **Spend caps.** Hard USD caps per run and per day are enforced inside the LLM client (`core/budget.py`).
- **Observability.** Langfuse is opt-in through a compose profile.

**Consequences.** Answer quality is bounded by the smaller model. The ablation report measures this rather than assuming it. Any number that depends on model quality is reported per profile.

## ADR-002: Structure-aware parsing, with format-specific parsers for legal text

**Context.** Citations must point to a clause, not just a document. Docling is excellent on PDFs and DOCX, but it flattens the hierarchy encoded in Federal Register XML, eCFR XML and GPO public-law text.

**Decision.** Docling (layout-aware, tables kept whole as Markdown) parses data-room PDFs, DOCX and MD, and also the NIST PDFs and the EU AI Act HTML. Regulations use dedicated parsers:
- **FR XML.** Preamble chunks follow the `HD1–HD6` heading path. Regulatory text in `SECTION` elements is chunked by clause, and Federal Register page numbers are tracked from `PRTPAGE`.
- **eCFR XML.** Each section is broken into CFR paragraph levels: (a), (1), (i), (A).
- **GPO public law.** Statute text is parsed by its indentation hierarchy, which yields exact clauses such as `4(a)(3)` and Statutes-at-Large pages.

A clause tree emits the largest node that fits in a chunk (about 1,800 characters) and splits deeper only when it has to.

**Consequences.** Citations look like `[doc:GENIUS-ACT-2025#s4(a)(3)]` or `[doc:CFR-12-1005.11#s1005.11(c)(2)]`, and the verifier can re-open exactly that clause. Downloaded XML is parsed with `defusedxml`.

## ADR-003: Contextual chunk headers

**Decision.** Every chunk is embedded with a header of the form `[title | issuer | section path | clause | version | effective date]`. The header is stored separately from the text. The ablation compares embedding with and without it.

## ADR-004: Prompt-injection defence at ingest

**Decision.** Every document is scanned at ingest for three signals:
1. Instruction-like text aimed at AI systems, scored with weighted patterns.
2. Hidden text in PDFs: white or near-transparent fill, or font size under 2pt, read through pdfium.
3. Payloads in document metadata.

A flagged document is quarantined. Its chunks are marked `trusted=false`, and any chunk containing the payload has its text replaced with a redaction marker before it can reach a prompt. Content-only signals need at least two independent patterns, so documents that merely *describe* prompt injection, such as NIST AI 600-1, are not flagged. Concealed payloads count more heavily.

**Consequences.** The seeded malicious addendum is caught by all three signals, with zero false positives across the other 55 documents. See `evals/report.md`.

## ADR-005: Anchor-based retrieval relevance

**Decision.** A gold source is a `(doc_id, verbatim anchor span)` pair. A retrieved chunk is relevant if it comes from the gold document and contains the anchor. This scores fixed-size and structure-aware chunkings the same way, which the ablation needs.

## ADR-006: Process analytics in DuckDB SQL; PM4Py optional

**Context.** PM4Py is AGPL-3.0. Ledgerline is a public repository that is meant to stay permissively licensed.

**Decision.** All metrics are whitelisted, parameterised SQL over a DuckDB file that tools only ever open read-only. The metrics cover cycle time, SLA breach, manual share, rework, variants, handoffs, resource load and bottlenecks, the directly-follows graph, late steps, and ticket categories. PM4Py is the optional `mining` extra, and it is used only for inductive-miner process trees in `process/discovery.py`. Every query gets a deterministic `query_id` and is logged together with its SQL, parameters and a result hash. A deliverable cites it as `[q:<id>]`, and the verifier re-runs it and compares the hash.

**Consequences.** Process numbers are reproducible and auditable, and the tools cannot write to the database (tested). Process maps degrade gracefully to the SQL directly-follows graph when PM4Py is not installed.

## ADR-007: A transparent, deterministic ROI model

**Decision.** Each opportunity's ROI is computed in plain Python with no LLM arithmetic, and it has exactly two kinds of input:
- **Volumes** come from `process_metrics` queries, cited as `[q:…]` and annualised over the measured data window (also a cited query).
- **Assumptions** come from `config/roi_assumptions.yaml`, cited as `[a:…]`. Each has a low, base and high value, a unit and a rationale.

**Volume method.** Hands-on effort is estimated in one of two ways:
- Where steps run back to back, as in reconciliation, it is the elapsed time before manual steps × an assumed hands-on share. This calibrates against the board deck's "three analysts fully utilized".
- Elsewhere it is manual step count × assumed touch minutes, because elapsed time there includes queueing.

**Financials.** NPV is computed over the horizon at the discount rate, with benefits starting after a ramp period and an annual run cost. The analysis also includes payback, a one-at-a-time tornado sensitivity, and conservative, base and optimistic scenarios. In the conservative and optimistic scenarios, cost-like assumptions move against value.

**Priority rules.** These are explicit, not learned:
- **deprioritize:** NPV ≤ 0
- **quick win:** time to value ≤ 3 months and implementation cost ≤ $80k
- **strategic bet:** NPV ≥ $100k
- **fill-in:** everything else

**Consequences.** Every figure in the ROI summary is reproducible, and changing an assumption changes the deliverable in a traceable way. Property-based tests check that the model is monotone.

## ADR-008: Selective graph extraction

**Context.** Extracting a full knowledge graph from about 9 MB of regulation is expensive and noisy. Most clauses in a rule preamble are not obligations, and many bind regulators rather than the client.

**Decision.** Only an explicit scope (`config/graph_scope.yaml`) becomes Requirement nodes:
- GENIUS Act §§2(16), 4 and 10
- Reg E §§1005.11 and 1005.13
- 31 CFR §§1022.210 and 1010.430
- the GOVERN, MAP and MANAGE passages of the NIST AI RMF
- the client's own vendor-policy minimum terms

Inside that scope, a modal-verb regex pre-filter sends only obligation-bearing chunks to the LLM. Controls are extracted from client policies, SOPs and contracts *as written, including deficiencies*. Requirements and controls share a fixed topic taxonomy. Candidate links come from topic overlap, and Haiku judges each applicable requirement against at most 8 candidate controls as satisfied, partial or not_satisfied.

The gap set is a graph query: applicable requirements with no `SATISFIES {status:'satisfied'}` edge. Findings are aggregated per topic, and split by counterparty for contracts. Every node and edge carries its source document, clause or page, and the extraction model. An in-memory twin of the store runs the same gap semantics in tests.

**Consequences.** A full graph build costs a few cents. Recall on the seeded gaps is measured in `evals/report.md`. Because the taxonomy is fixed, a gap outside it can be missed, which recall makes visible.

## ADR-009: Router, agent loop and verifier

**Router.** The router is cheap first and adaptive:
1. Regex intent classification picks a route (temporal, visual, numeric, diff, graph or hybrid), a corpus (data room or regulatory) and an `as_of` date.
2. A first pass runs the cheapest suitable tools. A temporal question gets `version_as_of` plus as-of-filtered search; a compliance question searches both corpora.
3. A lexical-coverage self-check decides whether to escalate. Numeric questions always escalate, because they need exact tools.
4. Escalation is a bounded (≤4-step) Claude tool-use loop over the stage's allow-listed tools, implemented with the Anthropic SDK directly. LangChain's chat wrappers would force `tool_choice`, which current models reject.
5. If the model still reports insufficient evidence after the cheap path, the router escalates once and retries.

**Answers.** An answer is structured output: sentences that each list evidence ids. Evidence is the only thing that can be cited. Each evidence item carries canonical citations: `[doc:…]`, `[q:…]`, `[a:…]` or `[calc]`.

**Verifier.** Each sentence goes through three checks:
1. It must cite at least one valid evidence id.
2. Every non-trivial number must round to a value in the cited evidence, allowing ×100 for percentages and about 1% for approximate figures of 100 or more.
3. A batched LLM entailment judge labels it supported or not.

Failing sentences are dropped and logged. If nothing survives, the answer is "insufficient evidence".

**Engagement.** The engagement is a LangGraph `StateGraph` of five stages. Inefficiency findings come from generic threshold detectors over mined metrics (`config/process_slas.yaml`), with no LLM involved. Memo sections are drafted by the LLM from findings and ROI evidence, then verified. The 90-day roadmap is deterministic.

**Caveat.** The detector thresholds were written by the same author who seeded the synthetic data. The report flags inefficiency recall as optimistic for that reason.

## ADR-010: Temporal (version-aware) retrieval

**Context.** Regulations change through proposed rules, final rules and effective dates. Answering from the wrong version is a material error.

**Decision.** Every regulatory document carries `lineage_id`, `publication_date`, `effective_date`, `valid_from` and `valid_to`. `valid_to` is set automatically to the publication date of the document that supersedes it, from the manifest's `supersedes` edges. These fields are copied onto every chunk and indexed as Qdrant payload, so an `as_of` query filters to `valid_from ≤ as_of < valid_to` with no look-ahead.

Legal status is computed separately (`version_as_of`):
- proposed (not binding)
- adopted but not yet effective
- effective

As a result, on 2026-11-16 the OCC GENIUS Act rule is correctly reported as *final but not effective until 2027-01-18*. `diff_versions` aligns regulatory text by CFR section and reports added, removed and modified sections with word-level changes, citing both versions. Lineage is data (`manifest.json`), not code, so re-running the fetcher picks up new final rules.

**Measured.** See *Temporal (as-of) correctness* in `evals/report.md`.

## ADR-011: ColPali-family visual retrieval, with VLM page reading

**Context.** Board-deck values such as monthly dispute breach rates and monthly KYC volumes exist only inside chart images. Text retrieval cannot answer those questions.

**Decision.** Data-room PDF pages are rendered and embedded with `vidore/colSmol-256M`, a ColPali-family late-interaction model. Each page becomes about 1,100 × 128 multi-vectors, stored in Qdrant with the MaxSim comparator. Indexing 13 pages takes about 30 s on an M2 GPU via MPS, with no CUDA required.

At query time the visual route retrieves the top pages. Claude then *reads* the page images to extract only the question-relevant values, which become evidence citing `[doc:ID#pN]`. Visual retrieval is an optional extra (`uv sync --extra visual`). Without it, a documented fallback does lexical search over page text, and that fallback **cannot** recover chart-only numbers.

**Why ColPali rather than OCR and captioning.** Late interaction over image patches keeps layout and chart semantics without a lossy captioning step at index time. The VLM only runs at query time, on one or two pages, which keeps cost proportional to visual questions.

## ADR-012: Guardrails and least privilege

- **Prompt injection.** Covered in ADR-004. Evidence marked `untrusted` is fenced as data in every prompt, and all system prompts say that evidence text is never an instruction.
- **Per-stage tool allow-lists.** These are enforced in `ToolRegistry.call`. A denied call raises an error and is audited.
- **Read-only data access:**
  - DuckDB is opened `read_only=True` for every tool query (tested).
  - The `process_metrics` tool runs only whitelisted, parameterised SQL.
  - The Postgres role `ledgerline_reader` (SELECT only) is provisioned for reporting.
  - Neo4j Community has no role-based access control. Graph tools therefore read only through fixed read queries or the exported JSON, and graph *writes* happen only in the offline `build_graph` job.
- **PII scrubbing.** Applied to audit records and OpenTelemetry spans before they are written or exported.
- **Spend caps.** Hard per-run and per-day caps, with thread-safe atomic updates to the ledger.
- **Secrets.** These live only in `.env`, which is gitignored. A CI check fails if README metrics drift from the eval report.
