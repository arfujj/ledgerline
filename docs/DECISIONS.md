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
