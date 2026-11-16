"""FastAPI application: engagements (SSE trace), review queue, deliverables, analytics, Q&A."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ledgerline import __version__
from ledgerline.core.audit import JsonlAuditSink
from ledgerline.core.settings import get_settings

app = FastAPI(
    title="Ledgerline",
    version=__version__,
    description="AI consulting copilot for fintech engagements (SYNTHETIC demo data). "
    "Not legal advice.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")
_RUNNING: dict[str, str] = {}


def _safe(x: str) -> str:
    if not _SAFE_ID.match(x):
        raise HTTPException(400, "invalid identifier")
    return x


def _root() -> Path:
    return get_settings().data_dir / "engagement"


@lru_cache(maxsize=1)
def _ctx() -> Any:
    from ledgerline.agents.context import AppContext

    return AppContext()


@lru_cache(maxsize=1)
def _queue() -> Any:
    from ledgerline.review.queue import ReviewQueue

    return ReviewQueue(get_settings().postgres_dsn)


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
    return [e.model_dump(mode="json") for e in sink.read(_safe(run_id))]


# --- engagements -----------------------------------------------------------------------------
@app.get("/engagements")
def list_engagements() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    root = _root()
    if not root.exists():
        return out
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        f = d / "engagement.json"
        if d.is_dir() and f.exists():
            e = json.loads(f.read_text())
            out.append(
                {
                    "run_id": d.name,
                    "cost_usd": e.get("cost_usd"),
                    "latency_s": e.get("latency_s"),
                    "model": e.get("model"),
                    "gaps": len(e.get("gaps", [])),
                    "inefficiencies": len(e.get("inefficiencies", [])),
                    "opportunities": len(e.get("opportunities", [])),
                }
            )
    for rid, status in _RUNNING.items():
        if status == "running" and rid not in {o["run_id"] for o in out}:
            out.insert(0, {"run_id": rid, "status": "running"})
    return out


@app.post("/engagements", status_code=202)
def start_engagement() -> dict[str, str]:
    from ledgerline.agents.engagement import Engagement

    run_id = f"eng-{uuid.uuid4().hex[:8]}"
    _RUNNING[run_id] = "running"

    def work() -> None:
        try:
            st = Engagement(_ctx(), run_id).run()
            _queue().enqueue(run_id, st["gaps"] + st["inefficiencies"] + st["security"])
            _RUNNING[run_id] = "done"
        except Exception as exc:
            _RUNNING[run_id] = f"error: {type(exc).__name__}: {exc}"

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": run_id, "status": "running"}


@app.get("/engagements/{run_id}")
def get_engagement(run_id: str) -> dict[str, Any]:
    f = _root() / _safe(run_id) / "engagement.json"
    if not f.exists():
        if run_id in _RUNNING:
            return {"run_id": run_id, "status": _RUNNING[run_id]}
        raise HTTPException(404, "unknown run")
    data: dict[str, Any] = json.loads(f.read_text())
    data["status"] = "done"
    return data


@app.get("/engagements/{run_id}/events")
async def engagement_events(run_id: str) -> EventSourceResponse:
    """Server-sent events: replays and then tails the audit log for this run."""
    run_id = _safe(run_id)
    path = get_settings().audit_log_path

    async def gen() -> Any:
        offset = 0
        idle = 0
        while idle < 600:
            new = []
            if path.exists():
                with path.open("r", encoding="utf-8") as fh:
                    fh.seek(offset)
                    new = fh.readlines()
                    offset = fh.tell()
            sent = False
            for line in new:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("run_id") != run_id:
                    continue
                sent = True
                yield {"event": ev["kind"], "data": json.dumps(ev)}
                if ev["kind"] == "stage" and ev["name"] == "engagement_end":
                    yield {"event": "done", "data": "{}"}
                    return
            idle = 0 if sent else idle + 1
            if not sent and _RUNNING.get(run_id, "done") != "running" and offset and idle > 3:
                yield {"event": "done", "data": "{}"}
                return
            await asyncio.sleep(0.5)

    return EventSourceResponse(gen())


# --- review -------------------------------------------------------------------------------
class ReviewAction(BaseModel):
    action: Literal["accept", "edit", "reject", "reset"]
    reviewer: str
    edits: dict[str, Any] | None = None
    reason: str = ""


@app.get("/engagements/{run_id}/review")
def review_items(run_id: str) -> dict[str, Any]:
    run_id = _safe(run_id)
    q = _queue()
    if not q.items(run_id):
        e = get_engagement(run_id)
        q.enqueue(run_id, e.get("gaps", []) + e.get("inefficiencies", []) + e.get("security", []))
    return {"items": q.items(run_id), "summary": q.summary(run_id)}


@app.post("/engagements/{run_id}/review/{finding_id}")
def review_action(run_id: str, finding_id: str, body: ReviewAction) -> dict[str, Any]:
    from ledgerline.review.queue import ReviewError

    try:
        res: dict[str, Any] = _queue().act(
            _safe(run_id), _safe(finding_id), body.action, body.reviewer, body.edits, body.reason
        )
        return res
    except ReviewError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/engagements/{run_id}/review-log")
def review_log(run_id: str) -> list[dict[str, Any]]:
    log: list[dict[str, Any]] = _queue().log(_safe(run_id))
    return log


# --- deliverables ---------------------------------------------------------------------------
@app.post("/engagements/{run_id}/export")
def export_deliverables(run_id: str) -> dict[str, Any]:
    from ledgerline.deliverables.build import build_all, export

    run_id = _safe(run_id)
    eng = get_engagement(run_id)
    review_items(run_id)
    q = _queue()
    paths = export(
        build_all(
            eng,
            q.reviewed_findings(run_id),
            get_settings().data_dir,
            Path("config"),
            q.summary(run_id),
        ),
        _root() / run_id / "deliverables",
    )
    return {
        name: {fmt: f"/engagements/{run_id}/deliverables/{name}.{fmt}" for fmt in p}
        for name, p in paths.items()
    }


@app.get("/engagements/{run_id}/deliverables/{filename}")
def get_deliverable(run_id: str, filename: str) -> FileResponse:
    f = _root() / _safe(run_id) / "deliverables" / _safe(filename)
    if not f.exists():
        raise HTTPException(404, "not exported yet")
    return FileResponse(f)


# --- analytics ------------------------------------------------------------------------------
@app.get("/process/{process}")
def process_view(process: str) -> dict[str, Any]:
    from ledgerline.process.discovery import process_map

    if process not in ("kyc", "disputes", "recon"):
        raise HTTPException(404, "unknown process")
    pm = _ctx().process
    m = process_map(pm, process)
    m["variants"] = pm.run("variants", process, top_n=8).records()
    m["bottlenecks"] = pm.run("bottlenecks", process, top_n=5).records()
    m["cycle_time"] = pm.run("cycle_time", process).records()[0]
    return m


@app.get("/opportunities")
def opportunities() -> dict[str, Any]:
    roi = _ctx().roi
    return {
        "base": [r.model_dump() for r in roi.evaluate_all()],
        "scenarios": {k: [r.model_dump() for r in v] for k, v in roi.scenarios().items()},
    }


class Ask(BaseModel):
    question: str
    allow_escalation: bool = True


@app.post("/ask")
def ask(body: Ask) -> dict[str, Any]:
    from ledgerline.agents.router import QAAgent

    if not 3 <= len(body.question) <= 1000:
        raise HTTPException(400, "question length must be 3-1000 characters")
    out: dict[str, Any] = QAAgent(
        _ctx(), f"qa-{uuid.uuid4().hex[:8]}", allow_escalation=body.allow_escalation
    ).answer(body.question)
    return out


@app.get("/regulations")
def regulations() -> list[dict[str, Any]]:
    from ledgerline.retrieval.temporal import version_as_of

    m = _ctx().manifest
    lineages: dict[str, list[dict[str, Any]]] = {}
    for d in m.docs:
        lineages.setdefault(d.lineage_id, []).append(d.model_dump(mode="json"))
    today = date.today()
    return [
        {
            "lineage_id": lin,
            "versions": docs,
            "status_today": version_as_of(m, lin, today).describe(),
        }
        for lin, docs in lineages.items()
    ]


@app.get("/regulations/{lineage_id}/diff")
def regulation_diff(lineage_id: str) -> dict[str, Any]:
    from ledgerline.retrieval.temporal import diff_versions

    ctx = _ctx()
    docs = sorted(
        (d for d in ctx.manifest.docs if d.lineage_id == _safe(lineage_id)),
        key=lambda d: d.publication_date or date.min,
    )
    if len(docs) < 2:
        raise HTTPException(404, "lineage has fewer than two versions")
    d = diff_versions(ctx.chunks, docs[-2].doc_id, docs[-1].doc_id, lineage_id)
    return {
        "lineage_id": lineage_id,
        "old": docs[-2].model_dump(mode="json"),
        "new": docs[-1].model_dump(mode="json"),
        "counts": d.counts(),
        "changes": [c.__dict__ for c in d.changes],
    }


# --- sources ----------------------------------------------------------------------------------
@app.get("/documents/{doc_id}")
def document(doc_id: str, locator: str = "") -> dict[str, Any]:
    """Source passage for a citation; includes a page-image URL when the source is a PDF."""
    ctx = _ctx()
    doc_id = _safe(doc_id)
    chunks = [c for c in ctx.chunks if c.doc_id == doc_id]
    if not chunks:
        raise HTTPException(404, "unknown document")
    hit = chunks
    if locator.startswith("p") and locator[1:].isdigit():
        hit = [c for c in chunks if c.page == int(locator[1:])] or chunks
    elif locator.startswith("s"):
        want = locator[1:]
        hit = (
            [c for c in chunks if c.clause and c.clause.startswith(want)]
            or [c for c in chunks if " > ".join(c.section_path).startswith(want)]
            or chunks
        )
    c0 = hit[0]
    docs = json.loads((get_settings().data_dir / "ingest" / "docs.json").read_text())
    meta: dict[str, Any] = next((d for d in docs if d["doc_id"] == doc_id), {})
    is_pdf = str(meta.get("source_path", "")).endswith(".pdf")
    return {
        "doc_id": doc_id,
        "title": c0.title,
        "issuer": c0.issuer,
        "locator": locator,
        "page": c0.page,
        "trusted": c0.trusted,
        "source_url": meta.get("source_url"),
        "passages": [
            {
                "chunk_id": c.chunk_id,
                "section": " > ".join(c.section_path),
                "clause": c.clause,
                "page": c.page,
                "text": c.text,
            }
            for c in hit[:3]
        ],
        "page_image": (f"/documents/{doc_id}/page/{c0.page or 1}.png" if is_pdf else None),
    }


@app.get("/documents/{doc_id}/page/{page}.png")
def page_image(doc_id: str, page: int) -> Response:
    import io

    import pypdfium2 as pdfium

    docs = json.loads((get_settings().data_dir / "ingest" / "docs.json").read_text())
    meta = next((d for d in docs if d["doc_id"] == _safe(doc_id)), None)
    if meta is None or not str(meta["source_path"]).endswith(".pdf"):
        raise HTTPException(404, "no page image for this document")
    pdf = pdfium.PdfDocument(meta["source_path"])
    if not 1 <= page <= len(pdf):
        raise HTTPException(404, "page out of range")
    buf = io.BytesIO()
    pdf[page - 1].render(scale=1.4).to_pil().save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png")


# --- evals ------------------------------------------------------------------------------------
@app.get("/evals")
def evals() -> dict[str, Any]:
    res = Path("evals/results")
    out: dict[str, Any] = {}
    for name in ("retrieval_summary", "temporal", "answer_key", "guardrails", "qa_summary"):
        f = res / f"{name}.json"
        if f.exists():
            data = json.loads(f.read_text())
            out[name] = data.get("summary", data) if name == "temporal" else data
    return out
