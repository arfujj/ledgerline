"""Graph node / finding models with provenance."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ledgerline.graph.taxonomy import Process, Topic

Severity = Literal["critical", "high", "medium", "low"]
CoverageStatus = Literal["satisfied", "partial", "not_satisfied", "not_applicable"]


class ExtractedRequirement(BaseModel):
    obligation: str = Field(description="One-sentence paraphrase of the obligation")
    actor: str = Field(description="Who must comply, e.g. 'permitted payment stablecoin issuer'")
    condition: str = Field(description="Trigger/condition, or empty string")
    topics: list[Topic]
    applies_to_client: bool = Field(
        description="Applies to a US money transmitter / card "
        "issuer planning to issue a USD stablecoin"
    )


class RequirementExtraction(BaseModel):
    requirements: list[ExtractedRequirement]


class ExtractedControl(BaseModel):
    statement: str = Field(description="What the control does, one sentence")
    process: Process
    owner_role: str
    control_type: Literal["preventive", "detective", "corrective", "contractual", "governance"]
    parameters: str = Field(description="Timing/thresholds/frequency, or empty string")
    topics: list[Topic]


class ControlExtraction(BaseModel):
    controls: list[ExtractedControl]


class Provenance(BaseModel):
    doc_id: str
    chunk_id: str
    clause: str | None = None
    page: int | None = None
    section: str = ""
    extraction_model: str = ""

    def cite(self) -> str:
        if self.clause:
            return f"[doc:{self.doc_id}#s{self.clause}]"
        if self.page is not None:
            return f"[doc:{self.doc_id}#p{self.page}]"
        return f"[doc:{self.doc_id}#s{self.section}]"


class Requirement(BaseModel):
    id: str
    text: str
    actor: str
    condition: str = ""
    topics: list[str]
    applies: bool = True
    kind: Literal["regulation", "standard", "internal_policy"] = "regulation"
    prov: Provenance


class Control(BaseModel):
    id: str
    text: str
    process: str
    owner_role: str
    control_type: str
    parameters: str = ""
    topics: list[str]
    prov: Provenance


class Vendor(BaseModel):
    id: str
    name: str
    tier: str
    processes: list[str]
    prov: Provenance


class Coverage(BaseModel):
    control_id: str
    requirement_id: str
    status: CoverageStatus
    rationale: str
    model: str


class Judgment(BaseModel):
    status: CoverageStatus
    rationale: str = Field(description="<= 60 words, refer to controls by id")
    severity: Severity
    recommendation: str = Field(description="<= 40 words, actionable")
    supporting_control_ids: list[str]


class Finding(BaseModel):
    finding_id: str
    category: Literal["compliance_gap", "inefficiency", "security"]
    title: str
    severity: Severity
    status: str
    topics: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    requirement_citations: list[str] = Field(default_factory=list)
    evidence_citations: list[str] = Field(default_factory=list)
    rationale: str
    recommendation: str
    owner: str = ""
    confidence: float = 0.5
