from datetime import date

from ledgerline.corpus.manifest import CorpusDoc, Manifest, link_lineage
from ledgerline.ingest.models import Chunk
from ledgerline.retrieval.temporal import diff_versions, version_as_of, visible_on


def _doc(i: str, t: str, pub: date, eff: date | None, sup: list[str] | None = None) -> CorpusDoc:
    return CorpusDoc(
        doc_id=i,
        lineage_id="occ",
        issuer="OCC",
        doc_type=t,
        title=i,
        source_url="u",
        local_path="p",
        sha256="s",
        retrieved_at="t",
        publication_date=pub,
        effective_date=eff,
        supersedes=sup or [],
    )


M = Manifest(
    generated_at="t",
    docs=link_lineage(
        [
            _doc("P", "proposed_rule", date(2026, 3, 2), None),
            _doc("F", "final_rule", date(2026, 10, 23), date(2027, 1, 18), ["P"]),
        ]
    ),
)


def test_version_as_of_windows() -> None:
    assert version_as_of(M, "occ", date(2026, 1, 1)).status == "not_yet_published"
    v = version_as_of(M, "occ", date(2026, 6, 1))
    assert (v.doc_id, v.status) == ("P", "proposed")
    v = version_as_of(M, "occ", date(2026, 11, 16))
    assert (v.doc_id, v.status, v.history) == ("F", "adopted_not_effective", ["P"])
    assert "not yet effective" in v.describe()
    v = version_as_of(M, "occ", date(2027, 2, 1))
    assert v.status == "effective"
    assert "in effect since 2027-01-18" in v.describe()
    assert "No version" in version_as_of(M, "occ", date(2025, 1, 1)).describe()


def _c(doc: str, clause: str, text: str, vf: date | None = None, vt: date | None = None) -> Chunk:
    return Chunk(
        chunk_id=f"{doc}::{clause}",
        doc_id=doc,
        corpus="regulatory",
        doc_type="x",
        title="t",
        issuer="i",
        clause=clause,
        text=text,
        header="",
        valid_from=vf,
        valid_to=vt,
    )


def test_visible_on() -> None:
    c = _c("P", "15.1", "x", date(2026, 3, 2), date(2026, 10, 23))
    assert visible_on(c, date(2026, 6, 1))
    assert not visible_on(c, date(2026, 10, 23))
    assert not visible_on(c, date(2026, 1, 1))


def test_diff_versions() -> None:
    chunks = [
        _c("P", "15.1(a)", "This part applies to issuers."),
        _c("P", "15.3(a)", "Reserves must be reported quarterly to the OCC by the issuer."),
        _c("P", "15.9", "Old section to be removed."),
        _c("F", "15.1(a)", "This part applies to issuers."),
        _c("F", "15.3(a)", "Reserves must be reported monthly to the OCC by the issuer."),
        _c("F", "15.4(b)", "New custody section."),
    ]
    d = diff_versions(chunks, "P", "F", "occ")
    by = {c.section: c for c in d.changes}
    assert by["15.1"].change == "unchanged"
    assert by["15.3"].change == "modified"
    assert any("quarterly" in x for x in by["15.3"].diff)
    assert any("monthly" in x for x in by["15.3"].diff)
    assert by["15.4"].change == "added"
    assert by["15.4"].new_cite == "[doc:F#s15.4]"
    assert by["15.9"].change == "removed"
    assert d.counts() == {"unchanged": 1, "modified": 1, "added": 1, "removed": 1}
    assert [c.section for c in d.changes] == ["15.1", "15.3", "15.4", "15.9"]
