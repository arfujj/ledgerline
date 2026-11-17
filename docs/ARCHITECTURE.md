# Ledgerline architecture

## System overview

```mermaid
flowchart LR
  subgraph Sources
    DR[(Synthetic NovaPay data room<br/>39 docs · 219K events · 5K tickets)]
    REG[(Public regulatory corpus<br/>GENIUS Act · OCC/FDIC/Treasury rules · FinCEN<br/>Reg E/Z · 31 CFR · NIST AI RMF · EU AI Act)]
  end

  subgraph Ingestion
    PARSE[Docling layout parsing<br/>+ FR/eCFR/public-law clause parsers]
    SCAN[Prompt-injection scan<br/>patterns · hidden PDF text · metadata]
    CHUNK[Clause-tree chunking<br/>+ contextual headers]
    PAGES[Page renderer]
  end

  subgraph Stores
    QD[(Qdrant<br/>dense+BM25 hybrid · as-of payload<br/>ColPali multivector pages)]
    NEO[(Neo4j<br/>Requirement · Control · Process<br/>Vendor · Role · Topic)]
    DUCK[(DuckDB read-only<br/>event logs + tickets)]
    PG[(Postgres<br/>review queue + log)]
  end

  subgraph Engine
    TOOLS[Tool registry<br/>per-stage allow-lists]
    ROUTER[Adaptive router<br/>cheap → escalate]
    GRAPH[LangGraph engagement]
    VERIFY[Grounding verifier]
    ROI[ROI model<br/>YAML assumptions]
  end

  subgraph Surfaces
    API[FastAPI + SSE]
    UI[Next.js UI]
    MCP[MCP server]
    DELIV[Memo · register · roadmap · ROI<br/>DOCX / PDF / MD]
  end

  DR --> PARSE
  REG --> PARSE
  PARSE --> SCAN --> CHUNK --> QD
  DR --> PAGES --> QD
  DR --> DUCK
  CHUNK -->|selective LLM extraction| NEO
  QD & NEO & DUCK --> TOOLS
  ROI --> TOOLS
  TOOLS --> ROUTER --> VERIFY
  TOOLS --> GRAPH --> VERIFY
  GRAPH --> PG
  VERIFY --> API --> UI
  VERIFY --> MCP
  PG --> DELIV
  API -. audit events .-> OTEL[OpenTelemetry → Langfuse / JSONL]
```

## Engagement state machine (LangGraph)

```mermaid
stateDiagram-v2
  [*] --> Discovery
  Discovery --> ProcessAnalysis: business map (verified)
  ProcessAnalysis --> OpportunitySizing: inefficiency findings [q:…]
  OpportunitySizing --> GapAnalysis: ROI + scenarios + tornado [q:…][a:…]
  GapAnalysis --> Synthesis: graph gaps [doc:…] + security findings
  Synthesis --> ReviewQueue: memo sections (verified) + 90-day roadmap
  ReviewQueue --> Deliverables: accept / edit / reject (logged)
  Deliverables --> [*]
```

| Stage | Allowed tools | Output |
|---|---|---|
| Discovery | `hybrid_search`, `graph_query` | Business map section (verified) and document inventory |
| Process analysis | `process_metrics`, `hybrid_search`, `calculator` | Inefficiency findings from generic threshold detectors |
| Opportunity sizing | `roi_model`, `process_metrics`, `calculator` | Base case, scenarios and sensitivity |
| Gap analysis | `graph_query`, `hybrid_search`, `diff_versions`, `version_as_of` | Gap findings and prompt-injection security findings |
| Synthesis | `draft_section` | Memo sections (verified) and roadmap |

## Q&A router

```mermaid
flowchart TD
  Q[Question] --> R{Regex intent router}
  R -->|date / as of| T[version_as_of + as-of filtered hybrid]
  R -->|chart / board deck| V[ColPali page search + Claude page reading]
  R -->|metric language| N[escalate: process_metrics / roi_model]
  R -->|proposed vs final| D[diff_versions]
  R -->|comply / gap| G[graph gaps + both corpora]
  R -->|otherwise| H[hybrid search, corpus by entity]
  T & V & D & G & H --> S{Self-check:<br/>lexical coverage ≥ 0.6?}
  S -->|no| A[Agentic loop ≤4 steps<br/>Claude tool use over allow-listed tools]
  S -->|yes| ANS
  N --> A --> ANS[Answer: sentences + evidence ids]
  ANS --> I{Model says<br/>insufficient?}
  I -->|yes, not yet escalated| A
  I -->|no| VER[Verifier: citation · numbers · entailment]
  VER -->|survivors| OUT[Cited answer]
  VER -->|nothing survives| INS[“Insufficient evidence”]
```

## Citations and traceability

| Citation | Meaning | Resolved to |
|---|---|---|
| `[doc:GENIUS-ACT-2025#s4(a)(3)]` | Document clause | Statute text for that clause, plus the source URL |
| `[doc:BRD-2026-Q3#p1]` | Document page | Passage and rendered page image (clickable in the UI) |
| `[q:q_fccda94b27d8]` | Data query | Logged SQL, parameters and result hash; re-run by the verifier |
| `[a:automation_rate_recon_matching]` | Model assumption | Value, range, unit and rationale from `config/roi_assumptions.yaml` |
| `[calc]` | Deterministic arithmetic | Calculator tool (safe arithmetic only, no code execution) |

## Cost profile

Every LLM role uses Claude Haiku 5.5, through OpenRouter or the Anthropic API. Embeddings, BM25, reranking and ColPali all run locally. Responses and embeddings are cached on disk. Spend caps apply per run and per day. Measured costs are in `evals/report.md`.
