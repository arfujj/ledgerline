"""Idempotent, cached fetcher for the regulatory corpus. Failures are logged, not fatal."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from ledgerline.corpus.manifest import CorpusDoc, Manifest, link_lineage
from ledgerline.corpus.sources import Source

FR_API = "https://www.federalregister.gov/api/v1"
ECFR_API = "https://www.ecfr.gov/api/versioner/v1"
USER_AGENT = "ledgerline-corpus-fetcher/0.1"
FR_FIELDS = (
    "document_number",
    "type",
    "title",
    "publication_date",
    "effective_on",
    "agencies",
    "full_text_xml_url",
    "raw_text_url",
    "pdf_url",
    "html_url",
    "regulation_id_numbers",
)
_FR_TYPE = {"Rule": "final_rule", "Proposed Rule": "proposed_rule", "Notice": "guidance"}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


class Fetcher:
    def __init__(
        self,
        root: Path,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
    ) -> None:
        self.root = root
        self.raw_dir = root / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.cache_index_path = root / "http_cache.json"
        self.log_path = root / "fetch_log.jsonl"
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
            timeout=120.0,
        )
        self.sleep = sleep
        self.max_retries = max_retries
        self.cache: dict[str, dict[str, str]] = (
            json.loads(self.cache_index_path.read_text()) if self.cache_index_path.exists() else {}
        )
        self.network_calls = 0

    def _log(self, **kw: Any) -> None:
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": _now(), **kw}, sort_keys=True) + "\n")

    def _get(self, url: str, dest: Path | None = None, refresh: bool = False) -> bytes:
        """GET with on-disk cache; conditional request (ETag) when refreshing."""
        entry = self.cache.get(url)
        if dest is not None and entry and dest.exists() and not refresh:
            data = dest.read_bytes()
            if _sha(data) == entry.get("sha256"):
                return data
        headers = {}
        if refresh and entry and entry.get("etag") and dest is not None and dest.exists():
            headers["If-None-Match"] = entry["etag"]
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                self.network_calls += 1
                r = self.client.get(url, headers=headers)
                if r.status_code == 304 and dest is not None:
                    return dest.read_bytes()
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
                r.raise_for_status()
                data = r.content
                if dest is not None:
                    dest.write_bytes(data)
                    self.cache[url] = {"sha256": _sha(data), "etag": r.headers.get("etag", "")}
                    self.cache_index_path.write_text(
                        json.dumps(self.cache, indent=1, sort_keys=True)
                    )
                return data
            except httpx.HTTPError as exc:
                last_exc = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and status not in (429, 500, 502, 503, 504):
                    break
                self.sleep(2**attempt)
        assert last_exc is not None
        raise last_exc

    def _fr_meta(self, number: str) -> dict[str, Any]:
        qs = "&".join(f"fields[]={f}" for f in FR_FIELDS)
        meta_path = self.raw_dir / f"FR-{number}.meta.json"
        data = self._get(f"{FR_API}/documents/{number}.json?{qs}", meta_path)
        meta: dict[str, Any] = json.loads(data)
        return meta

    def fetch_one(self, src: Source, refresh: bool = False) -> CorpusDoc:
        dest = self.raw_dir / f"{src.doc_id}.{src.file_ext}"
        if src.kind == "federal_register":
            assert src.fr_document_number
            meta = self._fr_meta(src.fr_document_number)
            url = meta["full_text_xml_url"]
            data = self._get(url, dest, refresh)
            return CorpusDoc(
                doc_id=src.doc_id,
                lineage_id=src.lineage_id,
                issuer=src.issuer,
                doc_type=_FR_TYPE.get(meta["type"], "guidance"),
                title=meta["title"],
                source_url=meta["html_url"],
                local_path=str(dest.relative_to(self.root)),
                sha256=_sha(data),
                retrieved_at=_now(),
                publication_date=_d(meta["publication_date"]),
                effective_date=_d(meta.get("effective_on")),
                supersedes=list(src.supersedes),
                fr_document_number=src.fr_document_number,
                regulation_id_numbers=meta.get("regulation_id_numbers") or [],
                pdf_url=meta.get("pdf_url"),
                notes=src.notes,
            )
        if src.kind == "ecfr":
            assert src.ecfr_title
            assert src.ecfr_section
            current = self._ecfr_current_version(src.ecfr_title, src.ecfr_section)
            part = src.ecfr_section.split(".")[0]
            url = (
                f"{ECFR_API}/full/{current['issue_date']}/title-{src.ecfr_title}.xml"
                f"?part={part}&section={src.ecfr_section}"
            )
            data = self._get(url, dest, refresh)
            return CorpusDoc(
                doc_id=src.doc_id,
                lineage_id=src.lineage_id,
                issuer=src.issuer,
                doc_type=src.doc_type or "regulation",
                title=src.title,
                source_url=f"https://www.ecfr.gov/current/title-{src.ecfr_title}/"
                f"section-{src.ecfr_section}",
                local_path=str(dest.relative_to(self.root)),
                sha256=_sha(data),
                retrieved_at=_now(),
                publication_date=_d(current["amendment_date"]),
                effective_date=_d(current["amendment_date"]),
                notes=f"eCFR point-in-time text as of {current['issue_date']}. {src.notes}".strip(),
            )
        assert src.url
        data = self._get(src.url, dest, refresh)
        return CorpusDoc(
            doc_id=src.doc_id,
            lineage_id=src.lineage_id,
            issuer=src.issuer,
            doc_type=src.doc_type or "guidance",
            title=src.title,
            source_url=src.url,
            local_path=str(dest.relative_to(self.root)),
            sha256=_sha(data),
            retrieved_at=_now(),
            publication_date=_d(src.publication_date),
            effective_date=_d(src.effective_date),
            supersedes=list(src.supersedes),
            notes=src.notes,
        )

    def _ecfr_current_version(self, title: int, section: str) -> dict[str, Any]:
        part = section.split(".")[0]
        path = self.raw_dir / f"ecfr-versions-title-{title}-part-{part}.json"
        data = json.loads(self._get(f"{ECFR_API}/versions/title-{title}.json?part={part}", path))
        versions = [
            v
            for v in data["content_versions"]
            if v["identifier"] == section and not v.get("removed")
        ]
        if not versions:
            raise LookupError(f"No eCFR versions for {title} CFR {section}")
        latest: dict[str, Any] = max(versions, key=lambda v: (v["date"], v["issue_date"]))
        return latest

    def run(self, sources: list[Source], refresh: bool = False) -> Manifest:
        docs: list[CorpusDoc] = []
        for src in sources:
            try:
                doc = self.fetch_one(src, refresh)
                docs.append(doc)
                self._log(doc_id=src.doc_id, status="ok", sha256=doc.sha256)
            except Exception as exc:
                self._log(
                    doc_id=src.doc_id, status="error", error=f"{type(exc).__name__}: {exc}"[:500]
                )
        manifest = Manifest(generated_at=_now(), docs=link_lineage(docs))
        manifest.save(self.root / "manifest.json")
        return manifest
