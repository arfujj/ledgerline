"""Phase 1 acceptance: determinism and internal consistency of the synthetic data room."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synth import answer_key, metrics
from synth.documents import build_documents
from synth.eventlogs import simulate_disputes, simulate_kyc, simulate_recon, simulate_tickets
from synth.render import render
from synth.world import SYNTHETIC_BANNER, WORLD

ROOT = Path(__file__).resolve().parents[2]
DATAROOM = ROOT / "dataroom"
SMALL = dataclasses.replace(WORLD, kyc_cases=600, dispute_cases=500, tickets=400)


def _sim(seed: int) -> tuple[pd.DataFrame, ...]:
    rng = np.random.default_rng(seed)
    return (
        simulate_kyc(SMALL, rng),
        simulate_disputes(SMALL, rng),
        simulate_recon(SMALL, rng),
        simulate_tickets(SMALL, rng),
    )


def test_simulation_is_deterministic() -> None:
    a, b = _sim(3), _sim(3)
    for x, y in zip(a, b, strict=True):
        pd.testing.assert_frame_equal(x, y)
    assert not _sim(4)[0].equals(a[0])


def test_rendering_is_deterministic(tmp_path: Path) -> None:
    k, d, r, t = _sim(3)
    m = metrics.compute(k, d, r, t)
    docs = {s.doc_id: s for s in build_documents(SMALL, m)}
    for doc_id in ("POL-AML-001", "SOP-REC-001", "BRD-2026-Q3"):  # docx, md, pdf w/ charts
        p1 = render(docs[doc_id], tmp_path / "a")
        p2 = render(docs[doc_id], tmp_path / "b")
        assert p1.read_bytes() == p2.read_bytes(), doc_id


def test_people_in_logs_match_org_chart() -> None:
    k, d, r, _ = _sim(5)
    org = {p.name for p in WORLD.people}
    humans = set(
        pd.concat([k, d, r]).query("role not in ['CUSTOMER', 'SYSTEM', 'AI_AGENT']").resource
    )
    assert humans <= org
    edd = set(k[k.activity == "Enhanced Due Diligence Review"].resource)
    assert edd == {p.name for p in WORLD.people_by_role("COMPLIANCE_ANALYST")}


def test_answer_key_doc_ids_exist() -> None:
    k, d, r, t = _sim(5)
    m = metrics.compute(k, d, r, t)
    ids = {s.doc_id for s in build_documents(SMALL, m)}
    key = answer_key.build(m, 5)
    cited = {e["doc_id"] for item in key["gaps"] + key["inefficiencies"] for e in item["evidence"]}
    assert cited <= ids
    assert {s["doc_id"] for s in key["security"]} <= ids


needs_dataroom = pytest.mark.skipif(
    not (DATAROOM / "MANIFEST.json").exists(), reason="run scripts/generate_dataroom.py first"
)


@needs_dataroom
def test_generated_dataroom_targets() -> None:
    idx = json.loads((DATAROOM / "INDEX.json").read_text())
    assert 30 <= len(idx) <= 50
    logs = [pd.read_parquet(p) for p in (DATAROOM / "event_logs").glob("*.parquet")]
    assert 180_000 <= sum(len(x) for x in logs) <= 250_000
    recon = pd.read_parquet(DATAROOM / "event_logs" / "daily_reconciliation.parquet")
    assert abs(recon.is_manual.mean() - 0.40) <= 0.02
    assert len(pd.read_csv(DATAROOM / "support" / "support_tickets.csv")) == 5_000
    cutoff = pd.Timestamp(WORLD.data_extract_date) + pd.Timedelta(days=1)
    assert all(x.timestamp.max() < cutoff for x in logs)


@needs_dataroom
def test_every_document_is_labelled_synthetic() -> None:
    import docx
    import pypdfium2 as pdfium

    for entry in json.loads((DATAROOM / "INDEX.json").read_text()):
        path = DATAROOM / entry["path"]
        if path.suffix == ".md":
            text = path.read_text()
        elif path.suffix == ".docx":
            text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
        else:
            pdf = pdfium.PdfDocument(str(path))
            text = pdf[0].get_textpage().get_text_range()
        assert SYNTHETIC_BANNER in text.replace("\r", ""), entry["doc_id"]


def test_app_does_not_import_synth() -> None:
    src = ROOT / "src" / "ledgerline"
    offenders = [
        p
        for p in src.rglob("*.py")
        if "import synth" in p.read_text() or "from synth" in p.read_text()
    ]
    assert offenders == []
