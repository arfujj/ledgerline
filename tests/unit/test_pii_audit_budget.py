from pathlib import Path

import pytest

from ledgerline.core.audit import AuditEvent, JsonlAuditSink, MemoryAuditSink
from ledgerline.core.budget import BudgetExceeded, SpendTracker
from ledgerline.core.llm_cache import ResponseCache, request_key
from ledgerline.core.models_registry import cost_usd
from ledgerline.core.pii import scrub, scrub_text


@pytest.mark.parametrize(
    ("raw", "token"),
    [
        ("mail jane.doe@novapay.example now", "[EMAIL]"),
        ("ssn 123-45-6789", "[SSN]"),
        ("card 4111 1111 1111 1111", "[CARD]"),
        ("key sk-ant-abcdefghijkl", "[API_KEY]"),
        ("call (415) 555-0134", "[PHONE]"),
    ],
)
def test_scrub_text(raw: str, token: str) -> None:
    assert token in scrub_text(raw)


def test_scrub_nested() -> None:
    out = scrub({"a": ["x@y.com", ("123-45-6789",)], "n": 3})
    assert out == {"a": ["[EMAIL]", ("[SSN]",)], "n": 3}


def test_jsonl_sink_scrubs_and_reads(tmp_path: Path) -> None:
    sink = JsonlAuditSink(tmp_path / "a" / "audit.jsonl")
    sink.write(AuditEvent(run_id="r1", kind="tool_call", name="t", payload={"q": "a@b.com"}))
    sink.write(AuditEvent(run_id="r2", kind="stage", name="s"))
    events = sink.read("r1")
    assert len(events) == 1
    assert events[0].payload["q"] == "[EMAIL]"
    assert len(sink.read()) == 2
    assert JsonlAuditSink(tmp_path / "none.jsonl").read() == []


def test_memory_sink() -> None:
    sink = MemoryAuditSink()
    sink.write(AuditEvent(run_id="r", kind="stage", name="x", payload={"e": "a@b.co"}))
    assert sink.events[0].payload["e"] == "[EMAIL]"


def test_spend_tracker_caps(tmp_path: Path) -> None:
    t = SpendTracker(max_per_run=0.10, max_per_day=0.15, ledger_path=tmp_path / "spend.json")
    t.check("r1", 0.05)
    t.record("r1", 0.08)
    with pytest.raises(BudgetExceeded, match="Run r1"):
        t.check("r1", 0.05)
    t.record("r2", 0.05)
    assert t.day_spend() == pytest.approx(0.13)
    with pytest.raises(BudgetExceeded, match="Daily"):
        t.check("r3", 0.05)
    # Day ledger persists across instances
    t2 = SpendTracker(1.0, 0.15, tmp_path / "spend.json")
    assert t2.day_spend() == pytest.approx(0.13)
    assert SpendTracker(1, 1, None).day_spend() == 0.0


def test_cost_tiers() -> None:
    assert cost_usd("claude-haiku-5-5", 100_000, 0) == pytest.approx(0.01)
    assert cost_usd("claude-haiku-5-5", 0, 1_000_000) == pytest.approx(0.50)
    # Long-prompt tier above 100K input tokens: $0.50 / $2.50
    assert cost_usd("claude-haiku-5-5", 200_000, 1_000) == pytest.approx(0.1025)
    assert cost_usd("claude-haiku-5-5", 10, 0, cache_read_tokens=90_000) == pytest.approx(
        (10 * 0.10 + 90_000 * 0.01) / 1e6
    )
    assert cost_usd("claude-opus-5-5", 1_000_000, 1_000_000) == pytest.approx(24.0)
    with pytest.raises(KeyError):
        cost_usd("gpt-x", 1, 1)


def test_response_cache(tmp_path: Path) -> None:
    c = ResponseCache(tmp_path / "c.sqlite")
    k = request_key({"b": 1, "a": [1, 2]})
    assert k == request_key({"a": [1, 2], "b": 1})
    assert c.get(k) is None
    c.put(k, {"x": 1})
    assert c.get(k) == {"x": 1}
    c.close()
