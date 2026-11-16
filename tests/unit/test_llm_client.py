from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from ledgerline.core.audit import MemoryAuditSink
from ledgerline.core.budget import BudgetExceeded, SpendTracker
from ledgerline.core.llm import LLMClient, LLMRefusal
from ledgerline.core.llm_cache import ResponseCache
from ledgerline.core.settings import Settings


class Answer(BaseModel):
    value: int


def _usage(i: int = 1000, o: int = 200) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=i, output_tokens=o, cache_read_input_tokens=0, cache_creation_input_tokens=0
    )


class _Block(SimpleNamespace):
    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return dict(vars(self))


class FakeMessages:
    def __init__(self, stop_reason: str = "end_turn") -> None:
        self.calls: list[dict[str, Any]] = []
        self.stop_reason = stop_reason

    def create(self, **kw: Any) -> SimpleNamespace:
        self.calls.append(kw)
        content = [
            _Block(type="text", text="hello [q:q1]"),
            _Block(type="tool_use", id="tu1", name="calculator", input={"expr": "1+1"}),
        ]
        return SimpleNamespace(
            content=content,
            stop_reason=self.stop_reason,
            usage=_usage(),
            stop_details=SimpleNamespace(category="cyber", explanation="no"),
        )

    def parse(self, output_format: type[BaseModel], **kw: Any) -> SimpleNamespace:
        self.calls.append(kw)
        return SimpleNamespace(
            content=[_Block(type="text", text='{"value": 7}')],
            stop_reason="end_turn",
            usage=_usage(),
            parsed_output=output_format.model_validate({"value": 7}),
        )


def _client(settings: Settings, fake: FakeMessages, cache: bool = True) -> LLMClient:
    return LLMClient(
        settings,
        MemoryAuditSink(),
        SpendTracker(settings.max_usd_per_run, settings.max_usd_per_day, None),
        ResponseCache(settings.llm_cache_path) if cache else None,
        sdk=SimpleNamespace(messages=fake),
    )


def test_complete_text_tools_and_cache(settings: Settings) -> None:
    fake = FakeMessages()
    client = _client(settings, fake)
    msgs: Any = [{"role": "user", "content": "hi"}]
    tools: Any = [{"name": "calculator", "description": "d", "input_schema": {"type": "object"}}]
    r = client.complete(run_id="r", name="t", messages=msgs, system="sys", tools=tools)
    assert r.text.startswith("hello")
    assert r.tool_uses[0].name == "calculator"
    assert r.model == "claude-haiku-5-5"
    assert r.cost_usd == pytest.approx((1000 * 0.10 + 200 * 0.50) / 1e6)
    sent = fake.calls[0]
    assert sent["output_config"] == {"effort": "low"}
    assert sent["tool_choice"] == {"type": "auto"}
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}

    r2 = client.complete(run_id="r", name="t", messages=msgs, system="sys", tools=tools)
    assert r2.cached
    assert r2.cost_usd == 0.0
    assert len(fake.calls) == 1
    audit = client.audit
    assert isinstance(audit, MemoryAuditSink)
    assert [e.cached for e in audit.events] == [False, True]


def test_structured_output(settings: Settings) -> None:
    fake = FakeMessages()
    client = _client(settings, fake)
    msgs: Any = [{"role": "user", "content": "n?"}]
    r = client.complete(run_id="r", name="p", messages=msgs, output_model=Answer)
    assert r.parsed == Answer(value=7)
    r2 = client.complete(run_id="r", name="p", messages=msgs, output_model=Answer)
    assert r2.cached
    assert r2.parsed == Answer(value=7)


def test_refusal_raises(settings: Settings) -> None:
    client = _client(settings, FakeMessages(stop_reason="refusal"), cache=False)
    msgs: Any = [{"role": "user", "content": "x"}]
    with pytest.raises(LLMRefusal) as ei:
        client.complete(run_id="r", name="t", messages=msgs)
    assert ei.value.category == "cyber"


def test_budget_blocks_call(settings: Settings) -> None:
    fake = FakeMessages()
    s = settings.model_copy(update={"max_usd_per_run": 0.0})
    client = _client(s, fake, cache=False)
    msgs: Any = [{"role": "user", "content": "x"}]
    with pytest.raises(BudgetExceeded):
        client.complete(run_id="r", name="t", messages=msgs)
    assert fake.calls == []


def test_unknown_model_rejected(settings: Settings) -> None:
    client = _client(settings, FakeMessages(), cache=False)
    msgs: Any = [{"role": "user", "content": "x"}]
    with pytest.raises(KeyError):
        client.complete(run_id="r", name="t", messages=msgs, model="not-a-model")


def test_quality_profile_uses_opus(settings: Settings) -> None:
    fake = FakeMessages()
    client = _client(settings.model_copy(update={"model_profile": "quality"}), fake, cache=False)
    msgs: Any = [{"role": "user", "content": "x"}]
    r = client.complete(run_id="r", name="t", messages=msgs)
    assert r.model == "claude-opus-5-5"
    assert fake.calls[0]["output_config"] == {"effort": "medium"}
