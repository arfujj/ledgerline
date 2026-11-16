"""Phase 2: fetcher idempotency, failure logging, and lineage validation (no network)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from ledgerline.corpus.fetch import Fetcher
from ledgerline.corpus.manifest import CorpusDoc, LineageError, Manifest, link_lineage
from ledgerline.corpus.sources import SOURCES, Source, select


def _fr_meta(number: str, type_: str, pub: str, eff: str | None) -> dict[str, object]:
    return {
        "document_number": number,
        "type": type_,
        "title": f"Rule {number}",
        "publication_date": pub,
        "effective_on": eff,
        "agencies": [],
        "full_text_xml_url": f"https://fr.example/{number}.xml",
        "raw_text_url": "",
        "pdf_url": f"https://fr.example/{number}.pdf",
        "html_url": f"https://fr.example/{number}",
        "regulation_id_numbers": ["1557-AF41"],
    }


def _transport(calls: list[str], fail: set[str] | None = None) -> httpx.MockTransport:
    fail = fail or set()

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        calls.append(url)
        if any(f in url for f in fail):
            return httpx.Response(404)
        if "/documents/A-1.json" in url:
            return httpx.Response(200, json=_fr_meta("A-1", "Proposed Rule", "2026-03-02", None))
        if "/documents/A-2.json" in url:
            return httpx.Response(200, json=_fr_meta("A-2", "Rule", "2026-10-23", "2027-01-18"))
        if "versions/title-12.json" in url:
            return httpx.Response(
                200,
                json={
                    "content_versions": [
                        {
                            "identifier": "1005.11",
                            "date": "2017-01-01",
                            "issue_date": "2017-01-01",
                            "amendment_date": "2017-01-01",
                            "removed": False,
                        },
                        {
                            "identifier": "1005.11",
                            "date": "2019-04-01",
                            "issue_date": "2023-03-29",
                            "amendment_date": "2019-04-01",
                            "removed": False,
                        },
                    ]
                },
            )
        return httpx.Response(200, content=f"<doc>{url}</doc>".encode(), headers={"etag": "e1"})

    return httpx.MockTransport(handler)


SRCS = [
    Source(
        "FR-A-1",
        "federal_register",
        "lin",
        "small",
        "OCC",
        fr_document_number="A-1",
        file_ext="xml",
    ),
    Source(
        "FR-A-2",
        "federal_register",
        "lin",
        "small",
        "OCC",
        fr_document_number="A-2",
        file_ext="xml",
        supersedes=("FR-A-1",),
    ),
    Source(
        "CFR-X",
        "ecfr",
        "cfr",
        "small",
        "CFPB",
        "12 CFR 1005.11",
        "regulation",
        ecfr_title=12,
        ecfr_section="1005.11",
        file_ext="xml",
    ),
    Source(
        "STD",
        "url",
        "std",
        "small",
        "NIST",
        "Std",
        "standard",
        url="https://n.example/x.pdf",
        file_ext="pdf",
        publication_date="2023-01-26",
    ),
]


def test_fetch_lineage_and_idempotency(tmp_path: Path) -> None:
    calls: list[str] = []
    f = Fetcher(tmp_path, httpx.Client(transport=_transport(calls)), sleep=lambda _: None)
    m = f.run(SRCS)
    docs = m.by_id()
    assert docs["FR-A-1"].doc_type == "proposed_rule"
    assert docs["FR-A-1"].valid_to == date(2026, 10, 23)
    assert docs["FR-A-1"].superseded_by == "FR-A-2"
    assert docs["FR-A-2"].effective_date == date(2027, 1, 18)
    assert docs["CFR-X"].effective_date == date(2019, 4, 1)
    assert "2023-03-29" in calls[-2] or any("full/2023-03-29" in c for c in calls)
    assert Manifest.load(tmp_path / "manifest.json").docs[0].doc_id == "FR-A-1"

    calls2: list[str] = []
    f2 = Fetcher(tmp_path, httpx.Client(transport=_transport(calls2)), sleep=lambda _: None)
    f2.run(SRCS)
    assert f2.network_calls == 0
    assert calls2 == []


def test_failures_are_logged_not_fatal(tmp_path: Path) -> None:
    calls: list[str] = []
    f = Fetcher(
        tmp_path,
        httpx.Client(transport=_transport(calls, fail={"n.example"})),
        sleep=lambda _: None,
    )
    m = f.run(SRCS)
    assert "STD" not in m.by_id()
    log = [json.loads(x) for x in (tmp_path / "fetch_log.jsonl").read_text().splitlines()]
    assert any(e["doc_id"] == "STD" and e["status"] == "error" for e in log)


def test_retry_on_server_error(tmp_path: Path) -> None:
    attempts = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503) if attempts["n"] < 3 else httpx.Response(200, content=b"ok")

    f = Fetcher(
        tmp_path, httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None
    )
    m = f.run([SRCS[3]])
    assert m.docs[0].doc_id == "STD"
    assert attempts["n"] == 3


def _doc(i: str, lin: str, pub: str, sup: list[str] | None = None) -> CorpusDoc:
    return CorpusDoc(
        doc_id=i,
        lineage_id=lin,
        issuer="x",
        doc_type="proposed_rule",
        title=i,
        source_url="u",
        local_path="p",
        sha256="s",
        retrieved_at="t",
        publication_date=date.fromisoformat(pub),
        supersedes=sup or [],
    )


def test_lineage_cycle_detected() -> None:
    a = _doc("a", "l", "2026-01-01", ["b"])
    b = _doc("b", "l", "2026-02-01", ["a"])
    with pytest.raises(LineageError, match="Cycle"):
        link_lineage([a, b])


def test_lineage_cross_lineage_rejected() -> None:
    with pytest.raises(LineageError, match="across lineages"):
        link_lineage([_doc("a", "l1", "2026-01-01"), _doc("b", "l2", "2026-02-01", ["a"])])


def test_registry_is_consistent() -> None:
    ids = [s.doc_id for s in SOURCES]
    assert len(ids) == len(set(ids))
    small = {s.doc_id for s in select("small")}
    assert {"FR-2026-04089", "FR-2026-21706", "GENIUS-ACT-2025"} <= small
    assert len(select("full")) == len(SOURCES)
    for s in SOURCES:
        for old in s.supersedes:
            assert old in ids
            assert next(x for x in SOURCES if x.doc_id == old).lineage_id == s.lineage_id


MANIFEST = Path(__file__).resolve().parents[2] / "corpus" / "regulatory" / "manifest.json"


@pytest.mark.skipif(not MANIFEST.exists(), reason="corpus not fetched")
def test_fetched_manifest_lineage() -> None:
    m = Manifest.load(MANIFEST).by_id()
    if "FR-2026-21706" in m:
        assert m["FR-2026-04089"].superseded_by == "FR-2026-21706"
        assert m["FR-2026-21706"].effective_date == date(2027, 1, 18)
