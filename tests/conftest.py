from __future__ import annotations

from pathlib import Path

import pytest

from ledgerline.core.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=tmp_path,
        audit_log_path=tmp_path / "audit.jsonl",
        llm_cache_path=tmp_path / "cache.sqlite",
        max_usd_per_run=1.0,
        max_usd_per_day=5.0,
    )
