"""Audit log of every agent step, tool call and model call. PII is scrubbed before write."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from ledgerline.core.pii import scrub

EventKind = Literal["stage", "tool_call", "llm_call", "route", "verify", "review", "error"]


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str
    kind: EventKind
    stage: str | None = None
    name: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class AuditSink(Protocol):
    def write(self, event: AuditEvent) -> None: ...


class JsonlAuditSink:
    """Append-only JSONL sink; thread-safe."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, event: AuditEvent) -> None:
        record = scrub(event.model_dump(mode="json"))
        line = json.dumps(record, sort_keys=True)
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def read(self, run_id: str | None = None) -> list[AuditEvent]:
        if not self.path.exists():
            return []
        events = [
            AuditEvent.model_validate_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [e for e in events if run_id is None or e.run_id == run_id]


class MemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def write(self, event: AuditEvent) -> None:
        self.events.append(AuditEvent.model_validate(scrub(event.model_dump(mode="json"))))
