"""Layout-aware parsing (Docling) for PDF/DOCX/MD/HTML into heading-scoped sections."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ledgerline.ingest.models import Section

HEADER_RE = re.compile(
    r"Document ID: (?P<doc_id>\S+) \| Version (?P<version>\S+) \| Effective "
    r"(?P<effective>\d{4}-\d{2}-\d{2}) \| Owner: (?P<owner>.+)"
)
_BANNER = "SYNTHETIC: NovaPay Inc. is a fictional company"


@lru_cache(maxsize=1)
def _converter() -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def parse(path: Path) -> tuple[list[Section], dict[str, str]]:
    """Return sections plus header metadata found in the document (title, doc_id, ...)."""
    doc = _converter().convert(str(path)).document
    meta: dict[str, str] = {}
    sections: list[Section] = []
    heading: list[str] = []
    paras: list[str] = []
    page: int | None = None
    sec_page: int | None = None

    def flush() -> None:
        nonlocal paras
        if paras:
            sections.append(Section(path=list(heading), page=sec_page, paragraphs=paras))
            paras = []

    for item, _level in doc.iterate_items():
        label = item.label.value
        prov = getattr(item, "prov", None)
        if prov:
            page = prov[0].page_no
        text = (getattr(item, "text", "") or "").strip()
        if label in ("page_header", "page_footer"):
            continue
        if label == "title" or (label == "section_header" and "title" not in meta):
            meta.setdefault("title", text)
            if label == "title":
                continue
        if text.startswith(_BANNER):
            meta["synthetic"] = "true"
            continue
        m = HEADER_RE.search(text)
        if m:
            meta.update(m.groupdict())
            continue
        if label == "section_header":
            flush()
            heading = [] if text == meta.get("title") else [text]
            sec_page = page
            continue
        if label == "table":
            flush()
            md = item.export_to_markdown(doc)
            sections.append(Section(path=list(heading), page=page, kind="table", paragraphs=[md]))
            continue
        if label == "picture":
            continue  # visual path handles figures (Phase 5)
        if text:
            if not paras:
                sec_page = page
            paras.append(text)
    flush()
    return sections, meta
