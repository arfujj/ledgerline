"""Lazily-constructed application context shared by tools, agents, API and MCP server."""

from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path
from typing import Any

from ledgerline.core.audit import AuditSink, JsonlAuditSink
from ledgerline.core.budget import SpendTracker
from ledgerline.core.llm import LLMClient
from ledgerline.core.llm_cache import ResponseCache
from ledgerline.core.settings import Settings, get_settings
from ledgerline.corpus.manifest import Manifest
from ledgerline.ingest.models import Chunk
from ledgerline.ingest.pipeline import load_chunks


class AppContext:
    def __init__(
        self,
        settings: Settings | None = None,
        audit: AuditSink | None = None,
        config_dir: Path = Path("config"),
    ) -> None:
        self.settings = settings or get_settings()
        self.audit: AuditSink = audit or JsonlAuditSink(self.settings.audit_log_path)
        self.config_dir = config_dir

    @cached_property
    def llm(self) -> LLMClient:
        s = self.settings
        return LLMClient(
            s,
            self.audit,
            SpendTracker(s.max_usd_per_run, s.max_usd_per_day, s.data_dir / "spend.json"),
            ResponseCache(s.llm_cache_path) if s.llm_cache_enabled else None,
        )

    @cached_property
    def chunks(self) -> list[Chunk]:
        return load_chunks(self.settings.data_dir / "ingest" / "chunks.jsonl")

    @cached_property
    def manifest(self) -> Manifest:
        return Manifest.load(self.settings.corpus_dir / "manifest.json")

    @cached_property
    def store(self) -> Any:
        from qdrant_client import QdrantClient

        from ledgerline.retrieval.store import ChunkStore

        return ChunkStore(QdrantClient(url=self.settings.qdrant_url), "ll_hybrid")

    @cached_property
    def process(self) -> Any:
        from ledgerline.process.metrics import ProcessMetrics

        return ProcessMetrics(
            self.settings.data_dir / "process.duckdb", self.settings.data_dir / "queries"
        )

    @cached_property
    def roi(self) -> Any:
        from ledgerline.roi.model import ROIModel, load_assumptions, load_catalogue

        return ROIModel(
            load_assumptions(self.config_dir / "roi_assumptions.yaml"),
            load_catalogue(self.config_dir / "opportunities.yaml"),
            self.process,
        )

    def graph_findings(self) -> list[dict[str, Any]]:
        p = self.settings.data_dir / "graph" / "gap_findings.json"
        data: list[dict[str, Any]] = json.loads(p.read_text()) if p.exists() else []
        return data

    def graph_items(self, name: str) -> list[dict[str, Any]]:
        p = self.settings.data_dir / "graph" / f"{name}.json"
        data: list[dict[str, Any]] = json.loads(p.read_text()) if p.exists() else []
        return data
