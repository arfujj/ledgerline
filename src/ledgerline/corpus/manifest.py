"""Corpus manifest: per-document metadata and version lineage, with validation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field


class CorpusDoc(BaseModel):
    doc_id: str
    lineage_id: str
    issuer: str
    doc_type: str
    title: str
    source_url: str
    local_path: str
    sha256: str
    retrieved_at: str
    publication_date: date | None = None
    effective_date: date | None = None
    valid_from: date | None = None  # this text version is current from...
    valid_to: date | None = None  # ...until superseded (exclusive); None = still current
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    fr_document_number: str | None = None
    regulation_id_numbers: list[str] = Field(default_factory=list)
    pdf_url: str | None = None
    notes: str = ""


class Manifest(BaseModel):
    generated_at: str
    docs: list[CorpusDoc]

    def by_id(self) -> dict[str, CorpusDoc]:
        return {d.doc_id: d for d in self.docs}

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Manifest:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


class LineageError(ValueError):
    pass


def link_lineage(docs: list[CorpusDoc]) -> list[CorpusDoc]:
    """Fill superseded_by / valid_from / valid_to from declared `supersedes` edges."""
    by_id = {d.doc_id: d for d in docs}
    for d in docs:
        d.valid_from = d.valid_from or d.publication_date
    for d in docs:
        for old_id in d.supersedes:
            old = by_id.get(old_id)
            if old is None:
                continue  # predecessor outside the selected slice
            old.superseded_by = d.doc_id
            old.valid_to = d.publication_date
    validate_lineage(docs)
    return docs


def validate_lineage(docs: list[CorpusDoc]) -> None:
    by_id = {d.doc_id: d for d in docs}
    for d in docs:
        # No cycles: walk the supersedes chain.
        seen: set[str] = set()
        stack = list(d.supersedes)
        while stack:
            cur = stack.pop()
            if cur == d.doc_id:
                raise LineageError(f"Cycle in lineage involving {d.doc_id}")
            if cur in seen or cur not in by_id:
                continue
            seen.add(cur)
            stack.extend(by_id[cur].supersedes)
        for old_id in d.supersedes:
            old = by_id.get(old_id)
            if old is None:
                continue
            if old.lineage_id != d.lineage_id:
                raise LineageError(f"{d.doc_id} supersedes {old_id} across lineages")
            if old.valid_to is None:
                raise LineageError(f"Superseded doc {old_id} has no valid_to")
            if old.valid_from and old.valid_to and old.valid_to < old.valid_from:
                raise LineageError(f"{old_id} valid_to precedes valid_from")
