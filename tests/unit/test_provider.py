from pydantic import SecretStr

from ledgerline.core.audit import MemoryAuditSink
from ledgerline.core.budget import SpendTracker
from ledgerline.core.llm import LLMClient
from ledgerline.core.models_registry import provider_model_id
from ledgerline.core.settings import Settings


def test_provider_resolution(settings: Settings) -> None:
    s = settings.model_copy(update={"anthropic_api_key": None, "openrouter_api_key": None})
    assert s.resolved_provider() is None
    assert not s.llm_configured()
    s_or = s.model_copy(update={"openrouter_api_key": SecretStr("sk-or-x")})
    assert s_or.resolved_provider() == "openrouter"
    s_both = s_or.model_copy(update={"anthropic_api_key": SecretStr("sk-ant-x")})
    assert s_both.resolved_provider() == "anthropic"
    forced = s_both.model_copy(update={"llm_provider": "openrouter"})
    assert forced.resolved_provider() == "openrouter"


def test_model_id_mapping() -> None:
    assert provider_model_id("claude-haiku-5-5", "openrouter") == "anthropic/claude-haiku-5.5"
    assert provider_model_id("claude-haiku-5-5", "anthropic") == "claude-haiku-5-5"


def test_openrouter_sdk_uses_base_url(settings: Settings) -> None:
    s = settings.model_copy(
        update={"anthropic_api_key": None, "openrouter_api_key": SecretStr("sk-or-test")}
    )
    c = LLMClient(s, MemoryAuditSink(), SpendTracker(1, 1, None))
    assert c.provider == "openrouter"
    assert "openrouter.ai" in str(c.sdk.base_url)


def test_blank_key_is_unset() -> None:
    s = Settings(_env_file=None, ANTHROPIC_API_KEY="  ", OPENROUTER_API_KEY="sk-or-y")  # type: ignore[call-arg]
    assert s.anthropic_api_key is None
    assert s.resolved_provider() == "openrouter"
