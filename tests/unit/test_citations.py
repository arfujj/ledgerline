import pytest
from pydantic import ValidationError

from ledgerline.core.citations import (
    AssumptionCitation,
    Claim,
    DocCitation,
    QueryCitation,
    parse_citations,
    strip_citations,
)


def test_render_and_parse_roundtrip() -> None:
    cites = [
        DocCitation(doc_id="sop_kyc_v3", page=4),
        DocCitation(doc_id="cfr12-1005", clause="1005.11(b)(1)"),
        QueryCitation(query_id="q_recon_manual_share"),
        AssumptionCitation(assumption_id="hourly_cost_ops"),
    ]
    text = "Claim " + " ".join(c.render() for c in cites) + "."
    parsed = parse_citations(text)
    assert [c.render() for c in parsed] == [c.render() for c in cites]
    assert strip_citations(text) == "Claim ."


def test_doc_citation_requires_locator() -> None:
    with pytest.raises(ValidationError):
        DocCitation(doc_id="x")


def test_claim_requires_citation_or_flag() -> None:
    with pytest.raises(ValidationError):
        Claim(text="Reconciliation is 40% manual.")
    flagged = Claim(text="Unknown.", status="insufficient_evidence")
    assert flagged.citations == []
    ok = Claim(text="x", citations=[QueryCitation(query_id="q1")])
    assert ok.status == "unverified"


def test_claim_parses_discriminated_union() -> None:
    c = Claim.model_validate(
        {"text": "x", "citations": [{"kind": "assumption", "assumption_id": "a1"}]}
    )
    assert isinstance(c.citations[0], AssumptionCitation)
