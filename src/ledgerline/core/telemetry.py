"""OpenTelemetry export of the audit stream (stages, tool calls, LLM calls).

Every AuditEvent becomes a span with GenAI semantic-convention attributes. Exporters:
  LEDGERLINE_OTEL_EXPORTER=none  (default) | file (JSONL spans) | otlp (e.g. self-hosted Langfuse)
For Langfuse: LEDGERLINE_OTEL_ENDPOINT=http://localhost:3100/api/public/otel plus
LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY (sent as HTTP basic auth). Payloads are PII-scrubbed
before export, exactly as for the JSONL audit log.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from ledgerline.core.audit import AuditEvent, AuditSink
from ledgerline.core.pii import scrub


class JsonlSpanExporter(SpanExporter):
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Any) -> SpanExportResult:
        with self.path.open("a", encoding="utf-8") as fh:
            for s in spans:
                rs: ReadableSpan = s
                fh.write(
                    json.dumps(
                        {
                            "name": rs.name,
                            "trace_id": format(rs.context.trace_id, "032x"),
                            "span_id": format(rs.context.span_id, "016x"),
                            "start": rs.start_time,
                            "end": rs.end_time,
                            "attributes": dict(rs.attributes or {}),
                        },
                        default=str,
                    )
                    + "\n"
                )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def build_provider(
    kind: str, endpoint: str | None = None, file_path: Path | None = None
) -> TracerProvider | None:
    if kind == "none":
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": "ledgerline"}))
    if kind == "file":
        provider.add_span_processor(
            SimpleSpanProcessor(JsonlSpanExporter(file_path or Path("data/audit/spans.jsonl")))
        )
    elif kind == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        headers = {}
        pk, sk = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
        if pk and sk:
            headers["Authorization"] = "Basic " + base64.b64encode(f"{pk}:{sk}".encode()).decode()
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=(endpoint or "http://localhost:3100/api/public/otel") + "/v1/traces",
                    headers=headers,
                )
            )
        )
    else:
        raise ValueError(f"unknown OTel exporter {kind!r}")
    return provider


class TracingAuditSink:
    """Wraps an AuditSink; every written event is also emitted as an OpenTelemetry span."""

    def __init__(self, inner: AuditSink, provider: TracerProvider) -> None:
        self.inner = inner
        self.provider = provider
        self.tracer = provider.get_tracer("ledgerline")

    def write(self, event: AuditEvent) -> None:
        self.inner.write(event)
        end_ns = int(event.ts.timestamp() * 1e9)
        start_ns = end_ns - int(event.latency_ms * 1e6)
        attrs: dict[str, Any] = {
            "ledgerline.run_id": event.run_id,
            "langfuse.session.id": event.run_id,
            "ledgerline.kind": event.kind,
            "ledgerline.stage": event.stage or "",
            "ledgerline.cost_usd": event.cost_usd,
            "ledgerline.cached": event.cached,
            "ledgerline.payload": json.dumps(scrub(event.payload), default=str)[:4000],
        }
        if event.kind == "llm_call":
            attrs.update(
                {
                    "gen_ai.system": "anthropic",
                    "gen_ai.request.model": event.model or "",
                    "gen_ai.usage.input_tokens": event.input_tokens,
                    "gen_ai.usage.output_tokens": event.output_tokens,
                }
            )
        span = self.tracer.start_span(
            f"{event.kind}:{event.name}", start_time=start_ns, attributes=attrs
        )
        span.end(end_time=end_ns)

    def flush(self) -> None:
        self.provider.force_flush()


def wrap(sink: AuditSink, kind: str, endpoint: str | None, file_path: Path) -> AuditSink:
    provider = build_provider(kind, endpoint, file_path)
    if provider is None:
        return sink
    trace.set_tracer_provider(provider)
    return TracingAuditSink(sink, provider)
