"""FastAPI application. Phase 0: health and audit endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from ledgerline import __version__
from ledgerline.core.audit import JsonlAuditSink
from ledgerline.core.settings import get_settings

app = FastAPI(title="Ledgerline", version=__version__)


@app.get("/health")
def health() -> dict[str, Any]:
    s = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "model_profile": s.model_profile,
        "llm_configured": s.llm_configured(),
        "llm_provider": s.resolved_provider(),
    }


@app.get("/runs/{run_id}/audit")
def run_audit(run_id: str) -> list[dict[str, Any]]:
    sink = JsonlAuditSink(get_settings().audit_log_path)
    return [e.model_dump(mode="json") for e in sink.read(run_id)]
