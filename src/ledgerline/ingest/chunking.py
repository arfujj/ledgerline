"""Structure-aware chunking with contextual headers."""

from __future__ import annotations

from ledgerline.ingest.models import Chunk, DocMeta, Section

MAX_CHARS = 1800
MIN_CHARS = 200


def contextual_header(meta: DocMeta, section: Section) -> str:
    parts = [meta.title, meta.issuer]
    if section.path:
        parts.append(" > ".join(section.path))
    if section.clause:
        parts.append(f"clause {section.clause}")
    if meta.version:
        parts.append(f"version {meta.version}")
    eff = meta.effective_date or meta.publication_date
    if eff:
        parts.append(f"effective {eff.isoformat()}")
    elif meta.doc_type == "proposed_rule" and meta.publication_date:
        parts.append(f"proposed {meta.publication_date.isoformat()}")
    return "[" + " | ".join(parts) + "]"


def window(paragraphs: list[str], max_chars: int = MAX_CHARS) -> list[str]:
    """Greedy pack paragraphs into windows; split oversized paragraphs on sentences."""
    out: list[str] = []
    buf = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        pieces = [para]
        if len(para) > max_chars:
            pieces, cur = [], ""
            for sent in para.replace("; ", ";\n").replace(". ", ".\n").split("\n"):
                if cur and len(cur) + len(sent) + 1 > max_chars:
                    pieces.append(cur)
                    cur = sent
                else:
                    cur = f"{cur} {sent}".strip()
            if cur:
                pieces.append(cur)
            # Hard-wrap any piece that still exceeds the limit (no sentence boundaries).
            pieces = [p[i : i + max_chars] for p in pieces for i in range(0, len(p), max_chars)]
        for piece in pieces:
            if buf and len(buf) + len(piece) + 2 > max_chars:
                out.append(buf)
                buf = piece
            else:
                buf = f"{buf}\n\n{piece}" if buf else piece
    if buf:
        out.append(buf)
    # Merge a tiny trailing window into its predecessor.
    if len(out) >= 2 and len(out[-1]) < MIN_CHARS and len(out[-2]) + len(out[-1]) < max_chars * 1.3:
        last = out.pop()
        out[-1] = f"{out[-1]}\n\n{last}"
    return out


def chunk_sections(
    meta: DocMeta, sections: list[Section], max_chars: int = MAX_CHARS
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sec in sections:
        texts = (
            ["\n".join(sec.paragraphs)]
            if sec.kind == "table"
            else window(sec.paragraphs, max_chars)
        )
        header = contextual_header(meta, sec)
        for text in texts:
            chunks.append(
                Chunk(
                    chunk_id=f"{meta.doc_id}::{len(chunks):04d}",
                    doc_id=meta.doc_id,
                    corpus=meta.corpus,
                    doc_type=meta.doc_type,
                    title=meta.title,
                    issuer=meta.issuer,
                    version=meta.version,
                    section_path=sec.path,
                    clause=sec.clause,
                    page=sec.page,
                    kind=sec.kind,
                    effective_date=meta.effective_date,
                    publication_date=meta.publication_date,
                    valid_from=meta.valid_from,
                    valid_to=meta.valid_to,
                    lineage_id=meta.lineage_id,
                    text=text,
                    header=header,
                )
            )
    return chunks


def naive_chunks(meta: DocMeta, sections: list[Section], size: int = 1000) -> list[Chunk]:
    """Baseline for ablations: fixed-size character windows, no structure, no headers."""
    full = "\n\n".join("\n\n".join(s.paragraphs) for s in sections)
    out: list[Chunk] = []
    for i in range(0, len(full), size):
        out.append(
            Chunk(
                chunk_id=f"{meta.doc_id}::naive{i // size:04d}",
                doc_id=meta.doc_id,
                corpus=meta.corpus,
                doc_type=meta.doc_type,
                title=meta.title,
                issuer=meta.issuer,
                version=meta.version,
                valid_from=meta.valid_from,
                valid_to=meta.valid_to,
                lineage_id=meta.lineage_id,
                effective_date=meta.effective_date,
                publication_date=meta.publication_date,
                text=full[i : i + size],
                header="",
            )
        )
    return out
