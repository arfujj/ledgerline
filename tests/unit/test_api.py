from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ledgerline.api import app as api
from ledgerline.core.settings import get_settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LEDGERLINE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LEDGERLINE_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("LEDGERLINE_POSTGRES_DSN", f"sqlite:///{tmp_path / 'review.db'}")
    get_settings.cache_clear()
    api._queue.cache_clear()
    run = tmp_path / "engagement" / "eng-test"
    run.mkdir(parents=True)
    finding = {
        "finding_id": "F-GAP-01",
        "category": "compliance_gap",
        "title": "T",
        "severity": "high",
        "status": "partial",
        "evidence_citations": ["[doc:A#p1]"],
        "requirement_citations": [],
        "rationale": "r",
        "recommendation": "x",
        "owner": "o",
        "confidence": 0.8,
    }
    (run / "engagement.json").write_text(
        json.dumps(
            {
                "run_id": "eng-test",
                "gaps": [finding],
                "inefficiencies": [],
                "security": [],
                "opportunities": [],
                "memo": [],
                "roadmap": [],
                "cost_usd": 0.01,
                "latency_s": 1.0,
                "model": "m",
            }
        )
    )
    (tmp_path / "audit.jsonl").write_text(
        json.dumps(
            {
                "event_id": "e1",
                "ts": "2026-11-16T00:00:00Z",
                "run_id": "eng-test",
                "kind": "stage",
                "stage": "engagement",
                "name": "engagement_end",
                "model": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "cost_usd": 0.0,
                "latency_ms": 0.0,
                "cached": False,
                "payload": {},
            }
        )
        + "\n"
    )
    yield TestClient(api.app)
    get_settings.cache_clear()
    api._queue.cache_clear()


def test_health_and_ids(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/engagements/..%2Fetc").status_code in (400, 404)
    assert client.get("/engagements/bad id!").status_code == 400
    assert client.get("/engagements/nope").status_code == 404


def test_engagements_and_review_flow(client: TestClient) -> None:
    runs = client.get("/engagements").json()
    assert runs[0]["run_id"] == "eng-test"
    assert client.get("/engagements/eng-test").json()["status"] == "done"
    items = client.get("/engagements/eng-test/review").json()
    assert items["summary"] == {"pending": 1}
    r = client.post(
        "/engagements/eng-test/review/F-GAP-01",
        json={"action": "edit", "reviewer": "alice", "edits": {"severity": "low"}},
    )
    assert r.json()["status"] == "edited"
    bad = client.post(
        "/engagements/eng-test/review/F-GAP-01",
        json={"action": "edit", "reviewer": "alice", "edits": {"x": 1}},
    )
    assert bad.status_code == 400
    log = client.get("/engagements/eng-test/review-log").json()
    assert log[0]["after"]["severity"] == "low"
    assert client.get("/runs/eng-test/audit").json()[0]["name"] == "engagement_end"


def test_sse_replays_and_finishes(client: TestClient) -> None:
    with client.stream("GET", "/engagements/eng-test/events") as resp:
        body = "".join(resp.iter_text())
    assert "engagement_end" in body
    assert "event: done" in body


def test_ask_validation(client: TestClient) -> None:
    assert client.post("/ask", json={"question": "x"}).status_code == 400


def test_evals_endpoint(client: TestClient) -> None:
    assert isinstance(client.get("/evals").json(), dict)


def test_deliverable_404(client: TestClient) -> None:
    assert client.get("/engagements/eng-test/deliverables/memo.pdf").status_code == 404
