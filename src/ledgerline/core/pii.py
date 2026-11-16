"""PII scrubbing for logs and audit records. Conservative regexes; applied before any write."""

from __future__ import annotations

import re
from typing import Any

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b(?:\d[ \-]?){13,19}\b"), "[CARD]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{8,}\b"), "[API_KEY]"),
    (re.compile(r"(?<!\w)\+?1?[ .\-]?\(?\d{3}\)?[ .\-]\d{3}[ .\-]\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[IBAN]"),
]


def scrub_text(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def scrub(value: Any) -> Any:
    """Recursively scrub strings inside dicts/lists/tuples."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, tuple):
        return tuple(scrub(v) for v in value)
    return value
