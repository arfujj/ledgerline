from __future__ import annotations

from datetime import date
from pathlib import Path

from ledgerline.ingest.chunking import chunk_sections, contextual_header, naive_chunks, window
from ledgerline.ingest.clause_tree import build_tree, cfr_units, emit_sections
from ledgerline.ingest.models import DocMeta, Section
from ledgerline.ingest.regs import parse_fr_xml, parse_public_law_html

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def _meta(**kw: object) -> DocMeta:
    base: dict[str, object] = dict(
        doc_id="D1",
        corpus="regulatory",
        title="Rule",
        doc_type="final_rule",
        issuer="OCC",
        version="2026-1",
        effective_date=date(2027, 1, 18),
        source_path="x",
        sha256="s",
    )
    base.update(kw)
    return DocMeta(**base)  # type: ignore[arg-type]


def test_cfr_units_levels_and_inline_labels() -> None:
    paras = [
        "(a) Definition—(1) Types. The term means:",
        "(i) An unauthorized transfer;",
        "(ii) An incorrect transfer.",
        "(2) Exclusions.",
        "(b) Notice.",
        "(1) Timing.",
        "(h) Item h.",
        "(i) Item i letter.",
    ]
    levels = [(lvl, lbl) for lvl, lbl, _ in cfr_units(paras)]
    assert levels[:5] == [(1, "a"), (3, "i"), (3, "ii"), (2, "2"), (1, "b")]
    assert levels[-1] == (1, "i")  # (i) after (h) at level 1 is a letter


def test_emit_sections_splits_long_nodes() -> None:
    units = [(1, "a", "(a) " + "x" * 50), (2, "1", "(1) " + "y" * 50), (2, "2", "(2) short")]
    tree = build_tree(units)
    small = emit_sections(tree, "15.1", ["s"], max_chars=1000)
    assert [s.clause for s in small] == ["15.1(a)"]
    big = emit_sections(tree, "15.1", ["s"], max_chars=80)
    assert [s.clause for s in big] == ["15.1(a)", "15.1(a)(1)", "15.1(a)(2)"]


def test_parse_fr_xml_preamble_tables_and_regtext() -> None:
    secs = parse_fr_xml(FIX / "fr_sample.xml")
    pre = [s for s in secs if s.path and s.path[-1] == "I. Background"]
    assert pre[0].paragraphs == ["Background text one.", "Background text two."]
    assert pre[0].page is None or pre[0].page == 101
    tables = [s for s in secs if s.kind == "table"]
    assert "| Reserve | 100% |" in tables[0].paragraphs
    reg = {s.clause: s for s in secs if s.clause}
    assert set(reg) == {"15.1(a)", "15.1(b)"}
    assert reg["15.1(b)"].page == 102
    assert reg["15.1(a)"].path == ["Regulatory text", "§ 15.1 Scope."]


def test_parse_public_law() -> None:
    secs = parse_public_law_html(FIX / "law_sample.html")
    by = {s.clause: s for s in secs}
    assert "4(a)" in by or "4(a)(1)" in by
    flat = " ".join(" ".join(s.paragraphs) for s in secs)
    assert "<<NOTE" not in flat
    assert secs[0].path[0].startswith("SEC. 4. REQUIREMENTS FOR ISSUING PAYMENT STABLECOINS")
    deep = emit = [s for s in parse_public_law_html(FIX / "law_sample.html")]
    assert deep == emit
    sec5 = [s for s in secs if s.clause and s.clause.startswith("5")]
    assert sec5[0].clause == "5(a)"


def test_window_and_header() -> None:
    out = window(["a" * 100, "b" * 100, "c" * 2000], max_chars=250)
    assert all(len(x) <= 400 for x in out)
    assert "a" * 100 in out[0]
    m = _meta()
    h = contextual_header(m, Section(path=["II", "A"], clause="15.1(a)", paragraphs=["x"]))
    assert h == "[Rule | OCC | II > A | clause 15.1(a) | version 2026-1 | effective 2027-01-18]"
    pm = _meta(doc_type="proposed_rule", effective_date=None, publication_date=date(2026, 3, 2))
    assert "effective 2026-03-02" in contextual_header(pm, Section(path=[], paragraphs=["x"]))


def test_chunk_ids_and_naive() -> None:
    m = _meta()
    secs = [
        Section(path=["A"], paragraphs=["p" * 500]),
        Section(path=["T"], kind="table", paragraphs=["| a |", "| b |"]),
    ]
    chunks = chunk_sections(m, secs)
    assert [c.chunk_id for c in chunks] == ["D1::0000", "D1::0001"]
    assert chunks[1].kind == "table"
    assert chunks[0].embed_text.startswith("[Rule")
    assert chunks[0].locator() == "sA"
    naive = naive_chunks(m, secs, size=200)
    assert all(c.header == "" for c in naive)
    assert len(naive) == 3
