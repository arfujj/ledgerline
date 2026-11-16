from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from ledgerline.graph.extract import (
    control_chunks,
    extract_controls,
    extract_requirements,
    parse_vendors,
    requirement_chunks,
)
from ledgerline.graph.gaps import aggregate, candidates, run_gap_analysis
from ledgerline.graph.models import (
    Control,
    ControlExtraction,
    Coverage,
    ExtractedControl,
    ExtractedRequirement,
    Judgment,
    Provenance,
    Requirement,
    RequirementExtraction,
)
from ledgerline.graph.store import MemoryGraph
from ledgerline.ingest.models import Chunk

SCOPE = {
    "requirement_sources": [
        {"doc_id": "LAW", "clause_prefixes": ["4(a)"]},
        {"doc_id": "POL-VRM", "sections": ["4. Terms"], "kind": "internal_policy"},
    ],
    "control_doc_types": ["policy", "sop", "contract"],
    "obligation_regex": r"(?i)\b(shall|must)\b",
}


def _chunk(cid: str, doc: str, text: str, **kw: Any) -> Chunk:
    base: dict[str, Any] = dict(
        chunk_id=cid,
        doc_id=doc,
        corpus="regulatory",
        doc_type="x",
        title="t",
        issuer="i",
        text=text,
        header="[h]",
    )
    base.update(kw)
    return Chunk(**base)


def _req(i: str, topics: list[str], applies: bool = True) -> Requirement:
    return Requirement(
        id=i,
        text="must do X",
        actor="issuer",
        topics=topics,
        applies=applies,
        prov=Provenance(doc_id="LAW", chunk_id="c", clause="4(a)(3)"),
    )


def _ctl(i: str, topics: list[str], doc: str = "SOP-1") -> Control:
    return Control(
        id=i,
        text="does X quarterly",
        process="reserves",
        owner_role="Treasury",
        control_type="preventive",
        parameters="quarterly",
        topics=topics,
        prov=Provenance(doc_id=doc, chunk_id="k", section="3. Reporting"),
    )


class FakeLLM:
    """Returns canned structured outputs keyed by the output model type."""

    def __init__(self, judgment: Judgment) -> None:
        self.judgment = judgment
        self.profile = SimpleNamespace(main="fake-model")

    def complete(self, **kw: Any) -> Any:
        om = kw["output_model"]
        if om is RequirementExtraction:
            parsed: Any = RequirementExtraction(
                requirements=[
                    ExtractedRequirement(
                        obligation="Publish reserves monthly",
                        actor="issuer",
                        condition="",
                        topics=["reserve_reporting"],
                        applies_to_client=True,
                    )
                ]
            )
        elif om is ControlExtraction:
            parsed = ControlExtraction(
                controls=[
                    ExtractedControl(
                        statement="Quarterly attestation",
                        process="reserves",
                        owner_role="Treasury",
                        control_type="detective",
                        parameters="quarterly",
                        topics=["reserve_reporting"],
                    )
                ]
            )
        else:
            parsed = self.judgment
        return SimpleNamespace(parsed=parsed, model="fake-model")


def test_selective_scope() -> None:
    chunks = [
        _chunk("a", "LAW", "The issuer shall publish.", clause="4(a)(1)"),
        _chunk("b", "LAW", "Definitions only.", clause="4(a)(2)"),
        _chunk("c", "LAW", "The issuer shall X.", clause="5(a)"),
        _chunk("d", "POL-VRM", "Right to audit.", section_path=["4. Terms"]),
        _chunk(
            "e", "SOP-1", "Quarterly attestation is obtained.", corpus="dataroom", doc_type="sop"
        ),
        _chunk("f", "SOP-2", "Bad", corpus="dataroom", doc_type="sop", trusted=False),
    ]
    sel = requirement_chunks(chunks, SCOPE)
    assert [(c.chunk_id, k) for c, k in sel] == [("a", "regulation"), ("d", "internal_policy")]
    assert [c.chunk_id for c in control_chunks(chunks, SCOPE)] == []  # too short / untrusted
    long = _chunk("g", "SOP-1", "x" * 80, corpus="dataroom", doc_type="sop")
    assert [c.chunk_id for c in control_chunks([long], SCOPE)] == ["g"]


def test_extraction_with_provenance() -> None:
    llm: Any = FakeLLM(
        Judgment(
            status="partial",
            rationale="r",
            severity="high",
            recommendation="x",
            supporting_control_ids=[],
        )
    )
    reqs = extract_requirements(
        llm, [(_chunk("a", "LAW", "shall", clause="4(a)(3)"), "regulation")], "run", workers=1
    )
    assert reqs[0].prov.cite() == "[doc:LAW#s4(a)(3)]"
    assert reqs[0].prov.extraction_model == "fake-model"
    ctrls = extract_controls(
        llm,
        [_chunk("e", "SOP-1", "x", corpus="dataroom", section_path=["3. Reporting"])],
        "run",
        workers=1,
    )
    assert ctrls[0].prov.cite() == "[doc:SOP-1#s3. Reporting]"


def test_gap_analysis_end_to_end() -> None:
    g = MemoryGraph()
    g.add_requirement(_req("R1", ["reserve_reporting"]))
    g.add_requirement(_req("R2", ["token_freeze_capability"]))
    g.add_requirement(_req("R3", ["reserve_reporting"], applies=False))
    g.add_control(_ctl("C1", ["reserve_reporting"]))
    llm: Any = FakeLLM(
        Judgment(
            status="partial",
            rationale="Quarterly not monthly [C1]",
            severity="high",
            recommendation="Move to monthly",
            supporting_control_ids=["C1"],
        )
    )
    findings, judgments = run_gap_analysis(llm, g, "run", workers=1)
    assert set(judgments) == {"R1", "R2"}
    assert g.stats()["coverage_edges"] == 2  # both judged partial, C1 cited
    assert {f.status for f in findings} == {"partial"}
    f = next(x for x in findings if "reserve" in x.title.lower())
    assert f.evidence_citations == ["[doc:SOP-1#s3. Reporting]"]
    assert f.requirement_citations == ["[doc:LAW#s4(a)(3)]"]


def test_satisfied_requirement_is_not_a_gap() -> None:
    g = MemoryGraph()
    g.add_requirement(_req("R1", ["reserve_reporting"]))
    g.add_control(_ctl("C1", ["reserve_reporting"]))
    g.add_coverage(
        Coverage(
            control_id="C1", requirement_id="R1", status="satisfied", rationale="ok", model="m"
        )
    )
    assert g.unsatisfied_requirements() == []
    j = {
        "R1": Judgment(
            status="satisfied",
            rationale="ok",
            severity="low",
            recommendation="-",
            supporting_control_ids=["C1"],
        )
    }
    assert aggregate(g, j, {"C1": _ctl("C1", [])}, {}) == []


def test_candidates_rank_by_topic_overlap() -> None:
    r = _req("R", ["reserve_reporting", "reserve_composition"])
    cs = [
        _ctl("C1", ["reserve_reporting"]),
        _ctl("C2", ["reserve_reporting", "reserve_composition"]),
        _ctl("C3", ["cip_kyc"]),
    ]
    assert [c.id for c in candidates(r, cs)] == ["C2", "C1"]


def test_parse_vendors() -> None:
    t = (
        "| ID | Vendor | Service | Tier | Annual fee | Processes |\n|---|---|---|---|---|---|\n"
        "| V-A | Acme | KYC | critical | $1 | kyc, recon |"
    )
    vs = parse_vendors([_chunk("t", "REG-VND", t, kind="table", corpus="dataroom")])
    assert vs[0].id == "V-A"
    assert vs[0].processes == ["kyc", "recon"]
