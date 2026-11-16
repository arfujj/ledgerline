"""Thin, audited wrapper around the Anthropic SDK.

Responsibilities: model-profile selection, spend caps, response caching, cost accounting,
PII-scrubbed audit events, refusal handling, structured outputs via `messages.parse`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

import anthropic
from anthropic.types import MessageParam, ToolParam
from pydantic import BaseModel

from ledgerline.core.audit import AuditEvent, AuditSink
from ledgerline.core.budget import SpendTracker
from ledgerline.core.llm_cache import ResponseCache, request_key
from ledgerline.core.models_registry import (
    PRICES,
    PROFILES,
    Effort,
    ModelProfile,
    cost_usd,
    provider_model_id,
)
from ledgerline.core.settings import Settings

T = TypeVar("T", bound=BaseModel)

# Rough chars-per-token used only for the pre-call budget estimate.
_CHARS_PER_TOKEN = 3.0
_EST_OUTPUT_TOKENS_CAP = 2_000


class LLMRefusal(RuntimeError):
    def __init__(self, category: str | None, explanation: str | None) -> None:
        super().__init__(f"Model declined the request (category={category}): {explanation}")
        self.category = category
        self.explanation = explanation


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResult[T: BaseModel]:
    model: str
    text: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    latency_ms: float
    cached: bool
    parsed: T | None = None
    tool_uses: list[ToolUse] = field(default_factory=list)
    raw_content: list[dict[str, Any]] = field(default_factory=list)


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        audit: AuditSink,
        spend: SpendTracker,
        cache: ResponseCache | None = None,
        sdk: Any | None = None,
    ) -> None:
        self.settings = settings
        self.profile: ModelProfile = PROFILES[settings.model_profile]
        self.audit = audit
        self.spend = spend
        self.cache = cache
        self._sdk = sdk

    @property
    def provider(self) -> str:
        return self.settings.resolved_provider() or "anthropic"

    @property
    def sdk(self) -> Any:
        if self._sdk is None:
            if self.provider == "openrouter":
                key = self.settings.openrouter_api_key
                if key is None:
                    raise RuntimeError("OPENROUTER_API_KEY is not set")
                # OpenRouter serves the Anthropic Messages API; same SDK, different base URL.
                self._sdk = anthropic.Anthropic(
                    api_key=key.get_secret_value(), base_url=self.settings.openrouter_base_url
                )
            else:
                key = self.settings.anthropic_api_key
                self._sdk = anthropic.Anthropic(api_key=key.get_secret_value() if key else None)
        return self._sdk

    def _estimate(self, model: str, payload: dict[str, Any], max_tokens: int) -> float:
        in_tokens = int(len(json.dumps(payload, default=str)) / _CHARS_PER_TOKEN)
        return cost_usd(model, in_tokens, min(max_tokens, _EST_OUTPUT_TOKENS_CAP))

    def complete(
        self,
        *,
        run_id: str,
        name: str,
        messages: Sequence[MessageParam],
        system: str | None = None,
        stage: str | None = None,
        max_tokens: int = 4_000,
        effort: Effort | None = None,
        model: str | None = None,
        tools: Sequence[ToolParam] | None = None,
        output_model: type[T] | None = None,
    ) -> LLMResult[T]:
        """Run one Messages API call. `output_model` switches to structured outputs."""
        model = model or self.profile.main
        if model not in PRICES:
            raise KeyError(f"Model {model!r} has no registered price; refusing to call it")
        effort = effort or self.profile.default_effort

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": list(messages),
            "output_config": {"effort": effort},
        }
        if system:
            # Stable system prompt first, marked cacheable (prefix caching).
            payload["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = {"type": "auto"}

        key_material = dict(payload)
        if output_model is not None:
            key_material["output_schema"] = output_model.model_json_schema()
        key = request_key(key_material)

        if self.cache is not None and self.settings.llm_cache_enabled:
            hit = self.cache.get(key)
            if hit is not None:
                cached_result: LLMResult[T] = self._from_cache(hit, output_model)
                self._audit(run_id, stage, name, cached_result, payload)
                return cached_result

        self.spend.check(run_id, self._estimate(model, payload, max_tokens))

        wire = {**payload, "model": provider_model_id(model, self.provider)}
        start = time.perf_counter()
        if output_model is not None:
            response = self.sdk.messages.parse(output_format=output_model, **wire)
        else:
            response = self.sdk.messages.create(**wire)
        latency_ms = (time.perf_counter() - start) * 1000

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMRefusal(
                getattr(details, "category", None), getattr(details, "explanation", None)
            )

        usage = response.usage
        cache_read = usage.cache_read_input_tokens or 0
        cache_write = usage.cache_creation_input_tokens or 0
        cost = cost_usd(model, usage.input_tokens, usage.output_tokens, cache_write, cache_read)
        self.spend.record(run_id, cost)

        text = "".join(b.text for b in response.content if b.type == "text")
        tool_uses = [
            ToolUse(id=b.id, name=b.name, input=dict(b.input))
            for b in response.content
            if b.type == "tool_use"
        ]
        parsed: T | None = None
        if output_model is not None:
            parsed = response.parsed_output
        result: LLMResult[T] = LLMResult(
            model=model,
            text=text,
            stop_reason=response.stop_reason,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            cost_usd=cost,
            latency_ms=latency_ms,
            cached=False,
            parsed=parsed,
            tool_uses=tool_uses,
            raw_content=[b.model_dump(mode="json") for b in response.content],
        )
        if self.cache is not None and self.settings.llm_cache_enabled:
            self.cache.put(key, self._to_cache(result))
        self._audit(run_id, stage, name, result, payload)
        return result

    @staticmethod
    def _to_cache(result: LLMResult[Any]) -> dict[str, Any]:
        return {
            "model": result.model,
            "text": result.text,
            "stop_reason": result.stop_reason,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cache_read_tokens": result.cache_read_tokens,
            "cache_write_tokens": result.cache_write_tokens,
            "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms,
            "parsed": result.parsed.model_dump(mode="json") if result.parsed else None,
            "tool_uses": [{"id": t.id, "name": t.name, "input": t.input} for t in result.tool_uses],
            "raw_content": result.raw_content,
        }

    @staticmethod
    def _from_cache(hit: dict[str, Any], output_model: type[T] | None) -> LLMResult[T]:
        parsed = (
            output_model.model_validate(hit["parsed"])
            if output_model is not None and hit.get("parsed") is not None
            else None
        )
        return LLMResult(
            model=hit["model"],
            text=hit["text"],
            stop_reason=hit["stop_reason"],
            input_tokens=hit["input_tokens"],
            output_tokens=hit["output_tokens"],
            cache_read_tokens=hit["cache_read_tokens"],
            cache_write_tokens=hit["cache_write_tokens"],
            cost_usd=0.0,  # a cache hit costs nothing now
            latency_ms=0.0,
            cached=True,
            parsed=parsed,
            tool_uses=[ToolUse(**t) for t in hit["tool_uses"]],
            raw_content=hit["raw_content"],
        )

    def _audit(
        self,
        run_id: str,
        stage: str | None,
        name: str,
        result: LLMResult[Any],
        payload: dict[str, Any],
    ) -> None:
        self.audit.write(
            AuditEvent(
                run_id=run_id,
                kind="llm_call",
                stage=stage,
                name=name,
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_read_tokens=result.cache_read_tokens,
                cache_write_tokens=result.cache_write_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                cached=result.cached,
                payload={
                    "provider": self.provider,
                    "effort": payload["output_config"]["effort"],
                    "max_tokens": payload["max_tokens"],
                    "stop_reason": result.stop_reason,
                    "n_tools": len(payload.get("tools", [])),
                    "tool_uses": [t.name for t in result.tool_uses],
                },
            )
        )
