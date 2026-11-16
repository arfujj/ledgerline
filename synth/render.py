"""Render document specs to Markdown, DOCX, and PDF deterministically."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Pt
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from synth.world import SYNTHETIC_BANNER

rl_config.invariant = 1  # reproducible PDFs (fixed creation date and document ID)


@dataclass
class TableBlock:
    header: list[str]
    rows: list[list[str]]
    caption: str | None = None


@dataclass
class Bullets:
    items: list[str]


@dataclass
class ChartBlock:
    """A chart whose numbers appear only in the image (tests the visual retrieval path)."""

    draw: Callable[[plt.Axes], None]
    caption: str
    alt_text: str = ""  # NOT rendered into PDFs; kept only for the answer key / evals


@dataclass
class PageBreakBlock:
    pass


Block = str | TableBlock | Bullets | ChartBlock | PageBreakBlock


@dataclass
class Section:
    heading: str
    blocks: list[Block]


@dataclass
class DocSpec:
    doc_id: str
    title: str
    doc_type: str  # policy | sop | contract | board_deck | postmortem | org | memo | register
    fmt: str  # md | docx | pdf
    version: str
    effective: str
    owner: str
    sections: list[Section]
    folder: str
    hidden_text: str | None = None  # for the seeded prompt-injection document
    pdf_subject: str | None = None
    meta: dict[str, str] = field(default_factory=dict)


def _header_lines(spec: DocSpec) -> list[str]:
    return [
        SYNTHETIC_BANNER,
        f"Document ID: {spec.doc_id} | Version {spec.version} | Effective {spec.effective} "
        f"| Owner: {spec.owner}",
    ]


def to_markdown(spec: DocSpec) -> str:
    out = [f"# {spec.title}", ""] + [f"> {line}" for line in _header_lines(spec)] + [""]
    for sec in spec.sections:
        out += [f"## {sec.heading}", ""]
        for b in sec.blocks:
            if isinstance(b, str):
                out += [b, ""]
            elif isinstance(b, Bullets):
                out += [f"- {i}" for i in b.items] + [""]
            elif isinstance(b, TableBlock):
                if b.caption:
                    out += [f"*{b.caption}*", ""]
                out.append("| " + " | ".join(b.header) + " |")
                out.append("|" + "---|" * len(b.header))
                out += ["| " + " | ".join(r) + " |" for r in b.rows]
                out.append("")
            elif isinstance(b, ChartBlock):
                out += [f"*[Chart: {b.caption}]*", ""]
    return "\n".join(out).rstrip() + "\n"


def _normalize_zip(data: bytes) -> bytes:
    """Rewrite a zip (DOCX) with fixed timestamps so output bytes are reproducible."""
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in sorted(src.infolist(), key=lambda i: i.filename):
            zi = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(zi, src.read(info.filename))
    return buf.getvalue()


def to_docx(spec: DocSpec, path: Path) -> None:
    doc = Document()
    cp = doc.core_properties
    cp.title, cp.author, cp.subject = spec.title, "NovaPay (SYNTHETIC)", spec.doc_type
    import datetime as _dt

    fixed = _dt.datetime(2026, 1, 1)
    cp.created = cp.modified = fixed
    cp.last_printed = fixed
    cp.revision = 1
    doc.add_heading(spec.title, level=0)
    for line in _header_lines(spec):
        p = doc.add_paragraph(line)
        p.runs[0].font.size = Pt(8)
        p.runs[0].italic = True
    for sec in spec.sections:
        doc.add_heading(sec.heading, level=1)
        for b in sec.blocks:
            if isinstance(b, str):
                doc.add_paragraph(b)
            elif isinstance(b, Bullets):
                for item in b.items:
                    doc.add_paragraph(item, style="List Bullet")
            elif isinstance(b, TableBlock):
                if b.caption:
                    doc.add_paragraph(b.caption).runs[0].italic = True
                t = doc.add_table(rows=1, cols=len(b.header))
                t.style = "Table Grid"
                for c, h in zip(t.rows[0].cells, b.header, strict=True):
                    c.text = h
                for r in b.rows:
                    cells = t.add_row().cells
                    for c, v in zip(cells, r, strict=True):
                        c.text = v
            elif isinstance(b, ChartBlock):
                doc.add_picture(io.BytesIO(_chart_png(b)), width=Pt(400))
                doc.add_paragraph(b.caption).runs[0].italic = True
    buf = io.BytesIO()
    doc.save(buf)
    path.write_bytes(_normalize_zip(buf.getvalue()))


def _chart_png(b: ChartBlock) -> bytes:
    fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=110)
    b.draw(ax)
    ax.set_title(b.caption, fontsize=10)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", metadata={"Software": None})
    plt.close(fig)
    return buf.getvalue()


def to_pdf(spec: DocSpec, path: Path) -> None:
    styles = getSampleStyleSheet()
    small = styles["Italic"].clone("small", fontSize=7, leading=9, textColor=colors.grey)
    story: list[object] = [Paragraph(spec.title, styles["Title"])]
    story += [Paragraph(line, small) for line in _header_lines(spec)]
    story.append(Spacer(1, 10))
    if spec.hidden_text:
        hidden = styles["Normal"].clone("hidden", fontSize=1, leading=2, textColor=colors.white)
        story.append(Paragraph(spec.hidden_text, hidden))
    for sec in spec.sections:
        story.append(Paragraph(sec.heading, styles["Heading2"]))
        for b in sec.blocks:
            if isinstance(b, str):
                story.append(Paragraph(b, styles["BodyText"]))
            elif isinstance(b, Bullets):
                for item in b.items:
                    story.append(Paragraph(f"&bull; {item}", styles["BodyText"]))
            elif isinstance(b, TableBlock):
                if b.caption:
                    story.append(Paragraph(f"<i>{b.caption}</i>", styles["BodyText"]))
                cell = styles["BodyText"].clone("cell", fontSize=8, leading=10)
                data = [[Paragraph(f"<b>{h}</b>", cell) for h in b.header]]
                data += [[Paragraph(v, cell) for v in r] for r in b.rows]
                t = Table(data, repeatRows=1, hAlign="LEFT")
                t.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf3")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ]
                    )
                )
                story += [t, Spacer(1, 6)]
            elif isinstance(b, ChartBlock):
                story.append(Image(io.BytesIO(_chart_png(b)), width=6.2 * inch, height=3.3 * inch))
                story.append(Paragraph(f"<i>Figure: {b.caption}</i>", small))
            elif isinstance(b, PageBreakBlock):
                story.append(PageBreak())
        story.append(Spacer(1, 6))

    def _footer(canvas: object, doc: object) -> None:
        c = canvas
        c.saveState()  # type: ignore[attr-defined]
        c.setFont("Helvetica", 7)  # type: ignore[attr-defined]
        c.drawString(
            0.75 * inch,
            0.5 * inch,  # type: ignore[attr-defined]
            f"{spec.doc_id} v{spec.version} | SYNTHETIC | page {c.getPageNumber()}",
        )  # type: ignore[attr-defined]
        c.restoreState()  # type: ignore[attr-defined]

    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        title=spec.title,
        author="NovaPay (SYNTHETIC)",
        subject=spec.pdf_subject or spec.doc_type,
        creator="ledgerline-synth",
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.75 * inch,
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


def render(spec: DocSpec, root: Path) -> Path:
    folder = root / spec.folder
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{spec.doc_id}.{spec.fmt}"
    if spec.fmt == "md":
        path.write_text(to_markdown(spec), encoding="utf-8")
    elif spec.fmt == "docx":
        to_docx(spec, path)
    elif spec.fmt == "pdf":
        to_pdf(spec, path)
    else:
        raise ValueError(spec.fmt)
    return path
