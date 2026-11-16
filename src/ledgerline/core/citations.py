"""Citation types. Every claim in a deliverable must carry at least one citation.

String forms (used inline in drafts and parsed back by the verifier):
  [doc:<doc_id>#p<page>]          document page
  [doc:<doc_id>#s<clause>]        document section / clause (e.g. s1005.11(b))
  [q:<query_id>]                  logged, re-runnable data query
  [a:<assumption_id>]             ROI model assumption
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class DocCitation(BaseModel):
    kind: Literal["doc"] = "doc"
    doc_id: str
    page: int | None = None
    clause: str | None = None
    chunk_id: str | None = None

    @model_validator(mode="after")
    def _needs_locator(self) -> DocCitation:
        if self.page is None and self.clause is None:
            raise ValueError("DocCitation requires a page or a clause")
        return self

    def render(self) -> str:
        loc = f"p{self.page}" if self.page is not None else f"s{self.clause}"
        return f"[doc:{self.doc_id}#{loc}]"


class QueryCitation(BaseModel):
    kind: Literal["query"] = "query"
    query_id: str

    def render(self) -> str:
        return f"[q:{self.query_id}]"


class AssumptionCitation(BaseModel):
    kind: Literal["assumption"] = "assumption"
    assumption_id: str

    def render(self) -> str:
        return f"[a:{self.assumption_id}]"


Citation = Annotated[DocCitation | QueryCitation | AssumptionCitation, Field(discriminator="kind")]

_CITE_RE = re.compile(
    r"\[(?:doc:(?P<doc>[A-Za-z0-9_.\-]+)#(?:p(?P<page>\d+)|s(?P<clause>[^\]\s]+))"
    r"|q:(?P<q>[A-Za-z0-9_.\-]+)|a:(?P<a>[A-Za-z0-9_.\-]+))\]"
)


def parse_citations(text: str) -> list[DocCitation | QueryCitation | AssumptionCitation]:
    """Extract all inline citations from text, in order of appearance."""
    out: list[DocCitation | QueryCitation | AssumptionCitation] = []
    for m in _CITE_RE.finditer(text):
        if m.group("doc"):
            page = m.group("page")
            out.append(
                DocCitation(
                    doc_id=m.group("doc"),
                    page=int(page) if page else None,
                    clause=m.group("clause"),
                )
            )
        elif m.group("q"):
            out.append(QueryCitation(query_id=m.group("q")))
        else:
            out.append(AssumptionCitation(assumption_id=m.group("a")))
    return out


def strip_citations(text: str) -> str:
    return re.sub(r"\s+", " ", _CITE_RE.sub("", text)).strip()


ClaimStatus = Literal["supported", "unsupported", "insufficient_evidence", "unverified"]


class Claim(BaseModel):
    """An atomic sentence in a deliverable with its supporting citations."""

    text: str
    citations: list[Citation] = Field(default_factory=list)
    status: ClaimStatus = "unverified"
    verifier_note: str | None = None

    @model_validator(mode="after")
    def _cited_or_flagged(self) -> Claim:
        if not self.citations and self.status != "insufficient_evidence":
            raise ValueError("Claim without citations must be marked insufficient_evidence")
        return self
