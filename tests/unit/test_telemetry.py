import json
from pathlib import Path

import pytest

from ledgerline.core.audit import AuditEvent, MemoryAuditSink
from ledgerline.core.telemetry import TracingAuditSink, build_provider, wrap


def test_file_exporter_emits_scrubbed_genai_spans(tmp_path: Path) -> None:
    provider = build_provider("file", file_path=tmp_path / "spans.jsonl")
    assert provider is not None
    inner = MemoryAuditSink()
    sink = TracingAuditSink(inner, provider)
    sink.write(
        AuditEvent(
            run_id="r1",
            kind="llm_call",
            stage="qa",
            name="answer",
            model="claude-haiku-5-5",
            input_tokens=10,
            output_tokens=5,
            latency_ms=12.0,
            payload={"note": "mail a@b.com"},
        )
    )
    sink.flush()
    spans = [json.loads(x) for x in (tmp_path / "spans.jsonl").read_text().splitlines()]
    assert spans[0]["name"] == "llm_call:answer"
    a = spans[0]["attributes"]
    assert a["gen_ai.request.model"] == "claude-haiku-5-5"
    assert a["gen_ai.usage.input_tokens"] == 10
    assert a["langfuse.session.id"] == "r1"
    assert "[EMAIL]" in a["ledgerline.payload"]
    assert inner.events[0].name == "answer"


def test_none_and_bad_exporter(tmp_path: Path) -> None:
    sink = MemoryAuditSink()
    assert wrap(sink, "none", None, tmp_path / "s.jsonl") is sink
    with pytest.raises(ValueError, match="unknown"):
        build_provider("zipkin")
