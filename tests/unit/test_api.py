from fastapi.testclient import TestClient

from ledgerline.api.app import app


def test_health() -> None:
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_audit_empty_run() -> None:
    r = TestClient(app).get("/runs/does-not-exist/audit")
    assert r.status_code == 200
    assert r.json() == []
