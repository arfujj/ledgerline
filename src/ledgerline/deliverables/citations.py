"""Resolve citation strings into human-readable footnotes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

CITE_RE = re.compile(r"\[(?:doc:[^\]]+|q:[^\]]+|a:[^\]]+|calc)\]")


class CitationResolver:
    def __init__(self, data_dir: Path, config_dir: Path) -> None:
        docs_path = data_dir / "ingest" / "docs.json"
        docs = json.loads(docs_path.read_text()) if docs_path.exists() else []
        self.docs = {d["doc_id"]: d for d in docs}
        self.queries = data_dir / "queries"
        ap = config_dir / "roi_assumptions.yaml"
        self.assumptions: dict[str, Any] = (
            yaml.safe_load(ap.read_text())["assumptions"] if ap.exists() else {}
        )
        self.order: list[str] = []

    def number(self, cite: str) -> int:
        if cite not in self.order:
            self.order.append(cite)
        return self.order.index(cite) + 1

    def describe(self, cite: str) -> str:
        if cite == "[calc]":
            return "Deterministic calculation by Ledgerline."
        kind, _, rest = cite.strip("[]").partition(":")
        if kind == "doc":
            doc_id, _, loc = rest.partition("#")
            d = self.docs.get(doc_id, {})
            if re.fullmatch(r"s\d+(\.\d+)*[a-z]?(\([0-9A-Za-z]+\))*", loc):
                where = f"clause {loc[1:]}"
            elif re.fullmatch(r"p\d+", loc):
                where = f"page {loc[1:]}"
            else:
                where = f"section '{loc[1:]}'"
            title = d.get("title", doc_id)
            src = d.get("source_url") or ""
            return f"{title} ({doc_id}), {where}." + (f" {src}" if src else "")
        if kind == "q":
            p = self.queries / f"{rest}.json"
            if p.exists():
                q = json.loads(p.read_text())
                params = ", ".join(f"{k}={v}" for k, v in q["params"].items())
                return (
                    f"Data query {rest}: metric '{q['metric']}' ({params}) over NovaPay "
                    f"event logs; result hash {q['result_hash']}."
                )
            return f"Data query {rest}."
        if kind == "a":
            a = self.assumptions.get(rest)
            if a:
                return (
                    f"Model assumption '{rest}': base {a['base']} {a['unit']} "
                    f"(range {a['low']}-{a['high']}). {a['rationale']}"
                )
            return f"Model assumption {rest}."
        return cite

    def footnote(self, text: str) -> str:
        """Replace inline citations with [^n] markers (Markdown footnotes)."""
        return CITE_RE.sub(lambda m: f"[^{self.number(m.group(0))}]", text)

    def strip(self, text: str) -> tuple[str, list[int]]:
        nums = [self.number(m.group(0)) for m in CITE_RE.finditer(text)]
        return re.sub(r"\s+", " ", CITE_RE.sub("", text)).strip(), sorted(set(nums))
