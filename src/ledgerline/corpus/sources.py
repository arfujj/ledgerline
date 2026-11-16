"""Registry of public regulatory and standards sources.

Federal Register metadata (type, publication and effective dates) is fetched live from the
Federal Register API at fetch time; only document numbers and lineage are declared here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DocType = Literal["statute", "proposed_rule", "final_rule", "regulation", "guidance", "standard"]
SourceKind = Literal["federal_register", "ecfr", "url"]
Slice = Literal["small", "full"]


@dataclass(frozen=True)
class Source:
    doc_id: str
    kind: SourceKind
    lineage_id: str
    slice: Slice
    issuer: str
    title: str = ""  # filled from the API for federal_register sources
    doc_type: DocType | None = None  # inferred for federal_register sources
    fr_document_number: str | None = None
    ecfr_title: int | None = None
    ecfr_section: str | None = None
    url: str | None = None
    file_ext: str = "html"
    publication_date: str | None = None  # declared for non-FR sources
    effective_date: str | None = None
    supersedes: tuple[str, ...] = ()
    notes: str = ""


SOURCES: tuple[Source, ...] = (
    # --- GENIUS Act (statute) ------------------------------------------------------------
    Source(
        "GENIUS-ACT-2025",
        "url",
        "genius-act",
        "small",
        "U.S. Congress",
        "Guiding and Establishing National Innovation for U.S. Stablecoins Act (Public Law 119-27)",
        "statute",
        url="https://www.govinfo.gov/content/pkg/PLAW-119publ27/html/PLAW-119publ27.htm",
        publication_date="2025-07-18",
        effective_date="2027-01-18",
        notes="Effective the earlier of 18 months after enactment or 120 days after final "
        "implementing regulations; OCC states 2027-01-18.",
    ),
    # --- OCC GENIUS issuer rule: proposed -> final (core temporal demo) --------------------
    Source(
        "FR-2026-04089",
        "federal_register",
        "occ-genius-issuer-rule",
        "small",
        "Office of the Comptroller of the Currency",
        fr_document_number="2026-04089",
        file_ext="xml",
    ),
    Source(
        "FR-2026-21706",
        "federal_register",
        "occ-genius-issuer-rule",
        "small",
        "Office of the Comptroller of the Currency",
        fr_document_number="2026-21706",
        file_ext="xml",
        supersedes=("FR-2026-04089",),
    ),
    Source(
        "FR-2026-12692",
        "federal_register",
        "occ-genius-aml-rule",
        "full",
        "Office of the Comptroller of the Currency",
        fr_document_number="2026-12692",
        file_ext="xml",
    ),
    Source(
        "FR-2026-06974",
        "federal_register",
        "fdic-genius-rule",
        "full",
        "Federal Deposit Insurance Corporation",
        fr_document_number="2026-06974",
        file_ext="xml",
    ),
    Source(
        "FR-2026-06489",
        "federal_register",
        "treasury-genius-state-regimes",
        "full",
        "U.S. Department of the Treasury",
        fr_document_number="2026-06489",
        file_ext="xml",
    ),
    Source(
        "FR-2026-16796",
        "federal_register",
        "treasury-genius-issuance",
        "full",
        "U.S. Department of the Treasury",
        fr_document_number="2026-16796",
        file_ext="xml",
    ),
    # --- FinCEN AML/CFT program rule: 2024 NPRM superseded by 2026 NPRM -------------------
    Source(
        "FR-2024-14414",
        "federal_register",
        "fincen-aml-program-rule",
        "small",
        "Financial Crimes Enforcement Network",
        fr_document_number="2024-14414",
        file_ext="xml",
    ),
    Source(
        "FR-2026-07033",
        "federal_register",
        "fincen-aml-program-rule",
        "small",
        "Financial Crimes Enforcement Network",
        fr_document_number="2026-07033",
        file_ext="xml",
        supersedes=("FR-2024-14414",),
        notes="Withdraws and supersedes the July 3, 2024 NPRM.",
    ),
    # --- CFR sections in force (eCFR point-in-time) ----------------------------------------
    Source(
        "CFR-12-1005.11",
        "ecfr",
        "cfr-12-1005.11",
        "small",
        "Consumer Financial Protection Bureau",
        "12 CFR 1005.11 Procedures for resolving errors (Regulation E)",
        "regulation",
        ecfr_title=12,
        ecfr_section="1005.11",
        file_ext="xml",
    ),
    Source(
        "CFR-12-1005.13",
        "ecfr",
        "cfr-12-1005.13",
        "full",
        "Consumer Financial Protection Bureau",
        "12 CFR 1005.13 Administrative enforcement; record retention (Regulation E)",
        "regulation",
        ecfr_title=12,
        ecfr_section="1005.13",
        file_ext="xml",
    ),
    Source(
        "CFR-12-1026.13",
        "ecfr",
        "cfr-12-1026.13",
        "full",
        "Consumer Financial Protection Bureau",
        "12 CFR 1026.13 Billing error resolution (Regulation Z)",
        "regulation",
        ecfr_title=12,
        ecfr_section="1026.13",
        file_ext="xml",
    ),
    Source(
        "CFR-31-1022.210",
        "ecfr",
        "cfr-31-1022.210",
        "small",
        "Financial Crimes Enforcement Network",
        "31 CFR 1022.210 Anti-money laundering programs for money services businesses",
        "regulation",
        ecfr_title=31,
        ecfr_section="1022.210",
        file_ext="xml",
    ),
    Source(
        "CFR-31-1010.430",
        "ecfr",
        "cfr-31-1010.430",
        "small",
        "Financial Crimes Enforcement Network",
        "31 CFR 1010.430 Nature of records and retention period",
        "regulation",
        ecfr_title=31,
        ecfr_section="1010.430",
        file_ext="xml",
    ),
    # --- AI standards and EU AI Act ------------------------------------------------------
    Source(
        "NIST-AI-100-1",
        "url",
        "nist-ai-rmf",
        "small",
        "National Institute of Standards and Technology",
        "Artificial Intelligence Risk Management Framework (AI RMF 1.0)",
        "standard",
        url="https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf",
        file_ext="pdf",
        publication_date="2023-01-26",
        effective_date="2023-01-26",
    ),
    Source(
        "NIST-AI-600-1",
        "url",
        "nist-ai-rmf-genai-profile",
        "full",
        "National Institute of Standards and Technology",
        "AI RMF: Generative Artificial Intelligence Profile",
        "standard",
        url="https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf",
        file_ext="pdf",
        publication_date="2024-07-26",
        effective_date="2024-07-26",
    ),
    Source(
        "EU-AI-ACT-2024",
        "url",
        "eu-ai-act",
        "full",
        "European Union",
        "Regulation (EU) 2024/1689 (Artificial Intelligence Act)",
        "statute",
        url="https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689",
        publication_date="2024-07-12",
        effective_date="2024-08-01",
        notes="Entered into force 2024-08-01 with staged application dates.",
    ),
)


def select(slice_: Slice) -> list[Source]:
    return [s for s in SOURCES if slice_ == "full" or s.slice == "small"]
