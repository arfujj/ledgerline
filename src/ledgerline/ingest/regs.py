"""Structure-aware parsers for Federal Register XML, eCFR XML, and public-law text."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET  # types only; parsing uses defusedxml
from pathlib import Path

import defusedxml.ElementTree as SafeET

from ledgerline.ingest.clause_tree import build_tree, cfr_units, emit_sections
from ledgerline.ingest.models import Section

_WS = re.compile(r"\s+")
_HD_LEVEL = {"HED": 1, "HD1": 2, "HD2": 3, "HD3": 4, "HD4": 5, "HD5": 6, "HD6": 7}
_SKIP = {
    "FTNT",
    "FTREF",
    "PRTPAGE",
    "FRDOC",
    "BILCOD",
    "GID",
    "AMDPAR",
    "STARS",
    "CONTENTS",
    "LSTSUB",
    "AUTH",
    "SIG",
    "SUBJECT",
    "SECTNO",
}


def _text(el: ET.Element) -> str:
    parts: list[str] = []

    def walk(e: ET.Element) -> None:
        if e.tag in ("FTREF", "PRTPAGE"):
            if e.tail:
                parts.append(e.tail)
            return
        if e.text:
            parts.append(e.text)
        for c in e:
            walk(c)
        if e is not el and e.tail:
            parts.append(e.tail)

    walk(el)
    return _WS.sub(" ", "".join(parts)).strip()


def _table(el: ET.Element) -> list[str]:
    rows = []
    title = el.findtext("TTITLE")
    if title:
        rows.append(f"Table: {_WS.sub(' ', title).strip()}")
    heads = [_text(h) for h in el.iter("CHED")]
    if heads:
        rows.append("| " + " | ".join(heads) + " |")
    for row in el.iter("ROW"):
        rows.append("| " + " | ".join(_text(c) for c in row.findall("ENT")) + " |")
    return rows


def parse_fr_xml(path: Path) -> list[Section]:
    root = SafeET.parse(path).getroot()
    sections: list[Section] = []
    heads: list[tuple[int, str]] = []
    state: dict[str, int | None] = {"page": None, "sec_page": None}
    buf: list[str] = []

    def flush() -> None:
        if buf:
            sections.append(
                Section(
                    path=[h for _, h in heads] or ["Preamble"],
                    page=state["sec_page"],
                    paragraphs=list(buf),
                )
            )
            buf.clear()

    def walk(el: ET.Element) -> None:
        tag = el.tag
        if tag == "PRTPAGE" and el.get("P", "").isdigit():
            state["page"] = int(el.get("P", "0"))
            if not buf:
                state["sec_page"] = state["page"]
            return
        if tag == "HD":
            level = _HD_LEVEL.get(el.get("SOURCE", "HD1"), 2)
            flush()
            while heads and heads[-1][0] >= level:
                heads.pop()
            heads.append((level, _text(el).rstrip(":")))
            state["sec_page"] = state["page"]
            return
        if tag == "SECTION":
            flush()
            sectno = el.findtext("SECTNO") or ""
            subject = _WS.sub(" ", el.findtext("SUBJECT") or "").strip()
            m = re.search(r"(\d+\.\d+[a-z]?)", sectno)
            num = m.group(1) if m else sectno.strip()
            paras: list[str] = []
            pages: list[int | None] = []
            for child in el:
                for pp in [child] if child.tag == "PRTPAGE" else list(child.iter("PRTPAGE")):
                    if pp.get("P", "").isdigit():
                        state["page"] = int(pp.get("P", "0"))
                if child.tag in ("P", "FP") and _text(child):
                    paras.append(_text(child))
                    pages.append(state["page"])
            path_ = ["Regulatory text", f"§ {num} {subject}".strip()]
            units = cfr_units(paras)
            unit_pages = pages if len(units) == len(pages) else None
            tree = build_tree(units, unit_pages)
            sections.extend(emit_sections(tree, num, path_, state["page"]))
            for tbl in el.iter("GPOTABLE"):
                sections.append(
                    Section(
                        path=path_,
                        clause=num,
                        page=state["page"],
                        kind="table",
                        paragraphs=_table(tbl),
                    )
                )
            return
        if tag == "GPOTABLE":
            flush()
            sections.append(
                Section(
                    path=[h for _, h in heads],
                    page=state["page"],
                    kind="table",
                    paragraphs=_table(el),
                )
            )
            return
        if tag in ("P", "FP"):
            t = _text(el)
            if t:
                if not buf:
                    state["sec_page"] = state["page"]
                buf.append(t)
            # PRTPAGE can be nested inside a paragraph.
            for pp in el.iter("PRTPAGE"):
                if pp.get("P", "").isdigit():
                    state["page"] = int(pp.get("P", "0"))
            return
        if tag in _SKIP:
            return
        for child in el:
            walk(child)

    walk(root)
    flush()
    return [s for s in sections if any(p.strip() for p in s.paragraphs)]


def parse_ecfr_xml(path: Path) -> list[Section]:
    root = SafeET.parse(path).getroot()
    head = _WS.sub(" ", root.findtext("HEAD") or "").strip()
    num = root.get("N", "")
    paras = [_text(p) for p in root.iter("P") if _text(p)]
    tree = build_tree(cfr_units(paras))
    return emit_sections(tree, num, [head])


_NOTE = re.compile(r"<<NOTE:[^>]*>>")
_PAGE = re.compile(r"\[\[Page (\d+) STAT\. (\d+)\]\]")
_SEC = re.compile(r"^SEC\. (\d+)\.\s+(.*)$")
_LABELED = re.compile(r"^( +)\(([A-Za-z]{1,5}|\d{1,3})\)\s+(.*)$")


def parse_public_law_html(path: Path) -> list[Section]:
    """Parse GPO public-law text: SEC. headings plus indentation-based clause hierarchy."""
    raw = html.unescape(re.sub(r"<[^>]+>", "", path.read_text(encoding="utf-8", errors="ignore")))
    sections: list[Section] = []
    page: int | None = None
    sec_num, sec_title = "", ""
    units: list[tuple[int, str, str]] = []
    unit_pages: list[int | None] = []
    indents: list[int] = []
    sec_page: int | None = None

    def flush() -> None:
        if sec_num and units:
            tree = build_tree(units, unit_pages)
            sections.extend(
                emit_sections(tree, sec_num, [f"SEC. {sec_num}. {sec_title}"], sec_page)
            )

    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = _NOTE.sub("", lines[i]).rstrip()
        pm = _PAGE.search(line)
        if pm:
            page = int(pm.group(2))
            i += 1
            continue
        sm = _SEC.match(line.strip())
        if sm:
            flush()
            sec_num, sec_title = sm.group(1), _WS.sub(" ", sm.group(2)).strip()
            # Title may wrap onto the next line(s).
            while (
                i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith("    (")
            ):
                if _PAGE.search(lines[i + 1]):
                    break
                sec_title += " " + _NOTE.sub("", lines[i + 1]).strip()
                i += 1
            sec_title = sec_title.rstrip(".")
            units, unit_pages, indents, sec_page = [], [], [], page
            i += 1
            continue
        lm = _LABELED.match(line)
        if lm and sec_num:
            indent = len(lm.group(1))
            if indent not in indents:
                indents.append(indent)
                indents.sort()
            level = indents.index(indent) + 1
            units.append((level, lm.group(2), f"({lm.group(2)}) {lm.group(3).strip()}"))
            unit_pages.append(page)
        elif line.strip() and units:
            lvl, lbl, txt = units[-1]
            units[-1] = (lvl, lbl, f"{txt} {line.strip()}")
        elif line.strip() and sec_num and not units:
            units.append((1, "", line.strip()))
            unit_pages.append(page)
        i += 1
    flush()
    return sections
