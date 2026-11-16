"""Build the four deliverables (memo, findings register, 90-day roadmap, ROI summary) and
export them to Markdown, DOCX and PDF. Inline citations become numbered source notes."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from ledgerline.deliverables.citations import CitationResolver

BlockKind = Literal["h1", "h2", "p", "table", "note", "bullets"]
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
DISCLAIMER = (
    "AI-generated draft from a SYNTHETIC data room (NovaPay is fictional). Every "
    "statement is traceable to a source document, data query or model assumption "
    "listed under Sources. This is not legal advice."
)


@dataclass
class Block:
    kind: BlockKind
    text: str = ""
    rows: list[list[str]] = field(default_factory=list)
    header: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)


@dataclass
class Deliverable:
    name: str
    title: str
    blocks: list[Block]
    sources: list[tuple[int, str]]


def _cites_text(res: CitationResolver, cites: list[str]) -> str:
    return " ".join(f"[{res.number(c)}]" for c in cites)


MEMO_MAX_CITES = 3


def _sentence(res: CitationResolver, s: dict[str, Any], max_cites: int = MEMO_MAX_CITES) -> str:
    """Primary citations only: prefer data queries and client documents, then regulations."""
    cites = list(dict.fromkeys(s["cites"]))
    cites.sort(key=lambda c: 0 if c.startswith("[q:") else 1 if c.startswith("[doc:") else 2)
    return f"{s['text']} " + _cites_text(res, cites[:max_cites])


def _sources(res: CitationResolver) -> list[tuple[int, str]]:
    return [(i + 1, res.describe(c)) for i, c in enumerate(res.order)]


def _header(eng: dict[str, Any], review: dict[str, int]) -> list[Block]:
    status = ", ".join(f"{k}: {v}" for k, v in sorted(review.items())) or "not yet reviewed"
    return [
        Block(
            "note",
            f"Prepared by Ledgerline for NovaPay Inc. · {date.today():%B %d, %Y} "
            f"· run {eng.get('run_id', '')} · model {eng.get('model', '')} · "
            f"review status: {status}",
        ),
        Block("note", DISCLAIMER),
    ]


def memo(
    eng: dict[str, Any],
    findings: list[dict[str, Any]],
    res: CitationResolver,
    review: dict[str, int],
) -> Deliverable:
    blocks = [
        Block("h1", "AI Readiness & Compliance Assessment: Executive Memo"),
        *_header(eng, review),
    ]
    for sec in eng.get("memo", []):
        kept = [s for s in sec["sentences"] if s["status"] == "supported"]
        if not kept:
            continue
        blocks.append(Block("h2", sec["title"]))
        blocks.append(Block("p", " ".join(_sentence(res, s) for s in kept)))
    top = sorted(findings, key=lambda f: SEV_ORDER[f["severity"]])[:6]
    blocks.append(Block("h2", "Priority findings"))
    blocks.append(
        Block(
            "bullets",
            items=[
                f"{f['finding_id']} ({f['severity']}): {f['title']}. "
                + _cites_text(
                    res, (f.get("evidence_citations", []) + f.get("requirement_citations", []))[:3]
                )
                for f in top
            ],
        )
    )
    rm = eng.get("roadmap", [])
    if rm:
        blocks.append(Block("h2", "Next 90 days"))
        windows: dict[str, list[str]] = {}
        for it in rm:
            windows.setdefault(it["window"], []).append(it["action"].rstrip("."))
        blocks.append(
            Block(
                "bullets",
                items=[
                    f"{w}: " + "; ".join(a[:3]) + (f" (+{len(a) - 3} more)" if len(a) > 3 else "")
                    for w, a in windows.items()
                ],
            )
        )
    return Deliverable("executive_memo", "Executive Memo", blocks, _sources(res))


def findings_register(
    eng: dict[str, Any],
    findings: list[dict[str, Any]],
    res: CitationResolver,
    review: dict[str, int],
) -> Deliverable:
    rows = []
    for f in sorted(findings, key=lambda f: (SEV_ORDER[f["severity"]], f["finding_id"])):
        rows.append(
            [
                f["finding_id"],
                f["title"],
                f["severity"],
                f"{f['rationale']} {_cites_text(res, f.get('evidence_citations', []))}",
                _cites_text(res, f.get("requirement_citations", [])) or "-",
                f["recommendation"],
                f.get("owner") or "-",
                f.get("review_status", "pending"),
            ]
        )
    blocks = [
        Block("h1", "Findings Register"),
        *_header(eng, review),
        Block(
            "table",
            header=[
                "ID",
                "Finding",
                "Severity",
                "Evidence",
                "Requirement",
                "Recommendation",
                "Owner",
                "Review",
            ],
            rows=rows,
        ),
    ]
    return Deliverable("findings_register", "Findings Register", blocks, _sources(res))


def roadmap(
    eng: dict[str, Any],
    res: CitationResolver,
    review: dict[str, int],
    findings: list[dict[str, Any]],
) -> Deliverable:
    kept_ids = {f["finding_id"] for f in findings}
    rows = [
        [
            it["window"],
            it["track"].replace("_", " "),
            it["action"],
            it["owner"],
            it.get("value", "-"),
            f"{it['ref']} {_cites_text(res, it['citations'])}",
        ]
        for it in eng.get("roadmap", [])
        if it["type"] == "opportunity" or it["ref"] in kept_ids
    ]
    blocks = [
        Block("h1", "90-Day Roadmap"),
        *_header(eng, review),
        Block(
            "p",
            "Quick wins and critical remediations start in the first 30 days; "
            "strategic bets are staged across days 31-90 behind human-oversight "
            "and validation gates.",
        ),
        Block("table", header=["Window", "Track", "Action", "Owner", "Value", "Ref"], rows=rows),
    ]
    return Deliverable("roadmap_90_day", "90-Day Roadmap", blocks, _sources(res))


def roi_summary(
    eng: dict[str, Any], res: CitationResolver, review: dict[str, int], assumptions: dict[str, Any]
) -> Deliverable:
    opps = eng.get("opportunities", [])
    sc = {k: {o["id"]: o["npv_usd"] for o in v} for k, v in eng.get("scenarios", {}).items()}
    rows = [
        [
            o["id"],
            o["title"],
            o["priority"].replace("_", " "),
            f"{o['annual_hours_saved']:,.0f}",
            f"${o['annual_value_usd']:,.0f}",
            f"${o['implementation_cost_usd']:,.0f}",
            f"${sc.get('low', {}).get(o['id'], 0):,.0f} / ${o['npv_usd']:,.0f} / "
            f"${sc.get('high', {}).get(o['id'], 0):,.0f}",
            f"{o['payback_months']}" if o["payback_months"] else "n/a",
            _cites_text(res, o["citations"]),
        ]
        for o in opps
    ]
    sens_rows = []
    for oid, items in eng.get("sensitivity", {}).items():
        for s in items[:2]:
            sens_rows.append(
                [
                    oid,
                    s["assumption_id"],
                    f"${s['npv_low']:,.0f}",
                    f"${s['npv_high']:,.0f}",
                    _cites_text(res, [f"[a:{s['assumption_id']}]"]),
                ]
            )
    used = sorted({c[3:-1] for o in opps for c in o["citations"] if c.startswith("[a:")})
    arows = [
        [
            a,
            str(assumptions[a]["base"]),
            f"{assumptions[a]['low']}-{assumptions[a]['high']}",
            assumptions[a]["unit"],
            assumptions[a]["rationale"],
        ]
        for a in used
        if a in assumptions
    ]
    blocks = [
        Block("h1", "Automation Opportunity & ROI Summary"),
        *_header(eng, review),
        Block(
            "p",
            "Hours saved come from mined event logs (data queries); value, cost, "
            "ramp and discount rate come from the stated assumptions. NPV is "
            "3-year, shown as conservative / base / optimistic.",
        ),
        Block(
            "table",
            header=[
                "ID",
                "Opportunity",
                "Priority",
                "Hours/yr",
                "Value/yr",
                "Implementation",
                "NPV low/base/high",
                "Payback (mo)",
                "Sources",
            ],
            rows=rows,
        ),
        Block("h2", "Largest sensitivities (one-at-a-time, NPV)"),
        Block(
            "table",
            header=["Opportunity", "Assumption", "NPV at low", "NPV at high", "Source"],
            rows=sens_rows,
        ),
        Block("h2", "Assumptions appendix"),
        Block("table", header=["Assumption", "Base", "Range", "Unit", "Rationale"], rows=arows),
    ]
    return Deliverable("roi_summary", "ROI Summary", blocks, _sources(res))


def build_all(
    eng: dict[str, Any],
    findings: list[dict[str, Any]],
    data_dir: Path,
    config_dir: Path,
    review: dict[str, int],
) -> list[Deliverable]:
    import yaml

    assumptions = yaml.safe_load((config_dir / "roi_assumptions.yaml").read_text())["assumptions"]

    def r() -> CitationResolver:
        return CitationResolver(data_dir, config_dir)

    return [
        memo(eng, findings, r(), review),
        findings_register(eng, findings, r(), review),
        roadmap(eng, r(), review, findings),
        roi_summary(eng, r(), review, assumptions),
    ]


# --- renderers ----------------------------------------------------------------------------
def to_markdown(d: Deliverable) -> str:
    out: list[str] = []
    for b in d.blocks:
        if b.kind == "h1":
            out += [f"# {b.text}", ""]
        elif b.kind == "h2":
            out += [f"## {b.text}", ""]
        elif b.kind == "p":
            out += [b.text, ""]
        elif b.kind == "note":
            out += [f"> {b.text}", ""]
        elif b.kind == "bullets":
            out += [f"- {i}" for i in b.items] + [""]
        elif b.kind == "table":
            out.append("| " + " | ".join(b.header) + " |")
            out.append("|" + "---|" * len(b.header))
            out += [
                "| " + " | ".join(c.replace("|", "/").replace("\n", " ") for c in r) + " |"
                for r in b.rows
            ]
            out.append("")
    out += ["## Sources", ""] + [f"{n}. {t}" for n, t in d.sources]
    return "\n".join(out).rstrip() + "\n"


def to_docx(d: Deliverable, path: Path) -> None:
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.shared import Pt

    doc = Document()
    if any(b.kind == "table" and len(b.header) > 5 for b in d.blocks):
        sec = doc.sections[0]
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = sec.page_height, sec.page_width
    style = doc.styles["Normal"]
    style.font.size = Pt(9.5)
    for b in d.blocks:
        if b.kind == "h1":
            doc.add_heading(b.text, level=0)
        elif b.kind == "h2":
            doc.add_heading(b.text, level=1)
        elif b.kind == "p":
            doc.add_paragraph(b.text)
        elif b.kind == "note":
            p = doc.add_paragraph(b.text)
            p.runs[0].italic = True
            p.runs[0].font.size = Pt(8)
        elif b.kind == "bullets":
            for i in b.items:
                doc.add_paragraph(i, style="List Bullet")
        elif b.kind == "table":
            t = doc.add_table(rows=1, cols=len(b.header))
            t.style = "Light Grid Accent 1"
            for c, h in zip(t.rows[0].cells, b.header, strict=True):
                c.text = h
            for r in b.rows:
                for c, v in zip(t.add_row().cells, r, strict=True):
                    c.text = v
    doc.add_heading("Sources", level=1)
    for n, t in d.sources:
        p = doc.add_paragraph(f"{n}. {t}")
        p.runs[0].font.size = Pt(7.5)
    doc.save(str(path))


def to_pdf(d: Deliverable, path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    wide = any(b.kind == "table" and len(b.header) > 5 for b in d.blocks)
    pagesize = landscape(LETTER) if wide else LETTER
    st = getSampleStyleSheet()
    body = st["BodyText"].clone("b", fontSize=9.5, leading=12.5)
    small = st["BodyText"].clone("s", fontSize=7, leading=8.5, textColor=colors.grey)
    cell = st["BodyText"].clone("c", fontSize=7, leading=8.5)

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story: list[Any] = []
    for b in d.blocks:
        if b.kind == "h1":
            story.append(Paragraph(esc(b.text), st["Title"]))
        elif b.kind == "h2":
            story.append(Paragraph(esc(b.text), st["Heading2"]))
        elif b.kind == "p":
            story.append(Paragraph(esc(b.text), body))
        elif b.kind == "note":
            story.append(Paragraph(f"<i>{esc(b.text)}</i>", small))
        elif b.kind == "bullets":
            for i in b.items:
                story.append(Paragraph(f"&bull; {esc(i)}", body))
        elif b.kind == "table":
            data = [[Paragraph(f"<b>{esc(h)}</b>", cell) for h in b.header]]
            data += [[Paragraph(esc(c), cell) for c in r] for r in b.rows]
            t = Table(data, repeatRows=1, hAlign="LEFT")
            t.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf3")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(t)
        story.append(Spacer(1, 5))
    story.append(Paragraph("Sources", st["Heading2"]))
    story += [Paragraph(esc(f"{n}. {t}"), small) for n, t in d.sources]
    SimpleDocTemplate(
        str(path),
        pagesize=pagesize,
        title=d.title,
        author="Ledgerline",
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    ).build(story)


def export(deliverables: list[Deliverable], out_dir: Path) -> dict[str, dict[str, str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, dict[str, str]] = {}
    for d in deliverables:
        md = out_dir / f"{d.name}.md"
        md.write_text(to_markdown(d))
        docx_p, pdf_p = out_dir / f"{d.name}.docx", out_dir / f"{d.name}.pdf"
        to_docx(d, docx_p)
        to_pdf(d, pdf_p)
        paths[d.name] = {"md": str(md), "docx": str(docx_p), "pdf": str(pdf_p)}
    return paths


def pdf_page_count(path: Path) -> int:
    import pypdfium2 as pdfium

    with io.BytesIO(path.read_bytes()) as fh:
        return len(pdfium.PdfDocument(fh))
