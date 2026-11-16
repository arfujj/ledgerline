"""Chunk and section models shared by ingestion, indexing and retrieval."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Corpus = Literal["dataroom", "regulatory"]
ChunkKind = Literal["text", "table"]


class Section(BaseModel):
    """A structural unit produced by a parser before chunking."""

    path: list[str]  # heading path, e.g. ["II. Description", "A. Subpart A"]
    clause: str | None = None  # legal citation locator, e.g. "1005.11(c)" or "4(a)(3)"
    page: int | None = None  # PDF page or Federal Register page
    kind: ChunkKind = "text"
    paragraphs: list[str]


class DocMeta(BaseModel):
    doc_id: str
    corpus: Corpus
    title: str
    doc_type: str
    issuer: str
    version: str = ""
    effective_date: date | None = None
    publication_date: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    lineage_id: str | None = None
    source_path: str
    source_url: str | None = None
    sha256: str


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    corpus: Corpus
    doc_type: str
    title: str
    issuer: str
    version: str = ""
    section_path: list[str] = Field(default_factory=list)
    clause: str | None = None
    page: int | None = None
    kind: ChunkKind = "text"
    effective_date: date | None = None
    publication_date: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    lineage_id: str | None = None
    text: str
    header: str
    trusted: bool = True
    injection_flags: list[str] = Field(default_factory=list)

    @property
    def embed_text(self) -> str:
        return f"{self.header}\n{self.text}"

    def locator(self) -> str:
        if self.clause:
            return f"s{self.clause}"
        if self.page is not None:
            return f"p{self.page}"
        return f"s{' > '.join(self.section_path)}"
