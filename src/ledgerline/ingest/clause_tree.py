"""Build legal clause trees from labeled paragraphs and emit clause-level sections."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ledgerline.ingest.models import Section

_ROMAN = {
    "i",
    "ii",
    "iii",
    "iv",
    "v",
    "vi",
    "vii",
    "viii",
    "ix",
    "x",
    "xi",
    "xii",
    "xiii",
    "xiv",
    "xv",
    "xvi",
    "xvii",
    "xviii",
    "xix",
    "xx",
}
LABEL_RE = re.compile(r"^\(([A-Za-z]{1,5}|\d{1,3})\)\s*")
INLINE_RE = re.compile(r"[—-]{1,2}\s?\(([A-Za-z]{1,5}|\d{1,3})\)")


@dataclass
class Node:
    label: str
    text: str
    children: list[Node] = field(default_factory=list)
    page: int | None = None

    def full_text(self) -> str:
        return "\n".join([self.text, *(c.full_text() for c in self.children)]).strip()


def cfr_level(label: str, prev_by_level: dict[int, str]) -> int:
    """CFR paragraph levels: (a) -> 1, (1) -> 2, (i) -> 3, (A) -> 4, (<italic 1>) -> 5."""
    if label.isdigit():
        return 2
    if label.isupper():
        return 4
    if label in _ROMAN:
        prev1 = prev_by_level.get(1)
        # "(i)" right after "(h)", or "(v)" after "(u)", is a level-1 letter, not a numeral.
        if (
            prev1 is not None
            and len(label) == 1
            and len(prev1) == 1
            and ord(label) == ord(prev1) + 1
            and 2 not in prev_by_level
        ):
            return 1
        if 2 in prev_by_level:
            return 3
        return 1
    return 1


def build_tree(units: list[tuple[int, str, str]], pages: list[int | None] | None = None) -> Node:
    """units: (level, label, text) in document order; optional per-unit pages."""
    root = Node("", "")
    stack: list[tuple[int, Node]] = [(0, root)]
    for i, (level, label, text) in enumerate(units):
        while stack and stack[-1][0] >= level:
            stack.pop()
        node = Node(label, text, page=pages[i] if pages else None)
        stack[-1][1].children.append(node)
        stack.append((level, node))
    return root


def emit_sections(
    node: Node,
    prefix: str,
    path: list[str],
    page: int | None = None,
    max_chars: int = 1800,
    min_depth: int = 1,
    depth: int = 0,
) -> list[Section]:
    """Emit one section per node whose full text fits, splitting deeper when too long."""
    out: list[Section] = []
    clause = f"{prefix}({node.label})" if node.label else prefix
    page = node.page if node.page is not None else page
    full = node.full_text()
    if node.label and depth >= min_depth and (len(full) <= max_chars or not node.children):
        return [Section(path=path, clause=clause, page=page, paragraphs=[full])]
    if node.text.strip():
        out.append(Section(path=path, clause=clause or None, page=page, paragraphs=[node.text]))
    for child in node.children:
        child_clause_prefix = clause
        out += emit_sections(
            child, child_clause_prefix, path, page, max_chars, min_depth, depth + 1
        )
    return out


def cfr_units(paragraphs: list[str]) -> list[tuple[int, str, str]]:
    """Assign CFR levels to paragraphs that start with one or more labels, e.g. '(d)(1) ...'."""
    units: list[tuple[int, str, str]] = []
    prev: dict[int, str] = {}
    for para in paragraphs:
        m = LABEL_RE.match(para)
        if not m:
            if units:
                lvl, lbl, txt = units[-1]
                units[-1] = (lvl, lbl, f"{txt}\n{para}")
            else:
                units.append((1, "", para))
            continue
        label = m.group(1)
        level = cfr_level(label, prev)
        prev[level] = label
        for deeper in [k for k in prev if k > level]:
            del prev[deeper]
        units.append((level, label, para))
        # Inline nested label, e.g. "(a) Definition of error—(1) Types of ...".
        inline = INLINE_RE.search(para[:160])
        if inline:
            sub = inline.group(1)
            sub_level = cfr_level(sub, prev)
            if sub_level > level:
                prev[sub_level] = sub
    return units
