"""Prompt-injection detection for ingested documents.

Signals (any one flags the document; flagged chunks are quarantined as untrusted data):
  * instruction-like text addressed to AI systems (pattern score)
  * hidden text in PDFs: white or near-invisible fill, or font size < 2pt
  * payloads in document metadata (PDF info dictionary / DOCX core properties)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    (
        "ignore_instructions",
        re.compile(
            r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|all)\b.{0,20}"
            r"\b(instructions?|prompts?|rules)\b",
            re.I | re.S,
        ),
        0.5,
    ),
    (
        "addressed_to_ai",
        re.compile(
            r"\b(note|message|instructions?)\s+(to|for)\s+(ai|llm|assistant|language model|"
            r"automated reviewer|chatbot)s?\b",
            re.I,
        ),
        0.4,
    ),
    (
        "system_prompt_spoof",
        re.compile(
            r"\b(system (note|prompt|message)|<\s*/?\s*system\s*>|"
            r"\[INST\]|###\s*instruction)",
            re.I,
        ),
        0.4,
    ),
    (
        "output_manipulation",
        re.compile(r"\byou (must|should|will) (report|say|state|answer|respond|conclude)\b", re.I),
        0.3,
    ),
    ("concealment", re.compile(r"\bdo not (mention|reveal|disclose) (this|these)\b", re.I), 0.3),
    (
        "exfiltration",
        re.compile(
            r"\b(?:send|upload|exfiltrate|forward|transmit)\s+(?:all|any|the|your|this)?\s*"
            r"(?:\w+\s){0,4}(?:to\s+https?://|api keys?|credentials|passwords?)"
        ),
        0.5,
    ),
]
THRESHOLD = 0.6


@dataclass
class ScanResult:
    flagged: bool = False
    score: float = 0.0
    signals: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


def score_text(text: str) -> tuple[float, list[str], list[str]]:
    score, sigs, ev = 0.0, [], []
    for name, pat, weight in _PATTERNS:
        m = pat.search(text)
        if m:
            score += weight
            sigs.append(name)
            ev.append(text[max(0, m.start() - 40) : m.end() + 40].strip())
    return min(score, 1.0), sigs, ev


def _pdf_hidden_text(path: Path) -> tuple[str, str]:
    """Return (hidden_text, metadata_text) from a PDF using pypdfium2."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    pdf = pdfium.PdfDocument(str(path))
    meta = " ".join(v for v in pdf.get_metadata_dict().values() if isinstance(v, str))
    hidden: list[str] = []
    for page in pdf:
        tp = page.get_textpage()
        for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_TEXT]):
            r, g, b, a = (raw.c_uint(), raw.c_uint(), raw.c_uint(), raw.c_uint())
            raw.FPDFPageObj_GetFillColor(obj.raw, r, g, b, a)
            size = raw.c_float()
            raw.FPDFTextObj_GetFontSize(obj.raw, size)
            invisible = (r.value > 240 and g.value > 240 and b.value > 240) or a.value < 20
            tiny = 0 < size.value < 2.0
            if invisible or tiny:
                import ctypes

                n = raw.FPDFTextObj_GetText(obj.raw, tp.raw, None, 0)  # bytes incl. NUL
                if n > 2:
                    buf = (ctypes.c_ushort * (n // 2))()
                    raw.FPDFTextObj_GetText(obj.raw, tp.raw, buf, n)
                    hidden.append(bytes(buf).decode("utf-16-le", errors="ignore").rstrip("\x00"))
    pdf.close()
    return " ".join(hidden), meta


def _docx_metadata(path: Path) -> str:
    import docx

    cp = docx.Document(str(path)).core_properties
    return " ".join(str(v) for v in (cp.title, cp.subject, cp.keywords, cp.comments) if v)


def scan_document(path: Path, full_text: str) -> ScanResult:
    res = ScanResult()
    s, sig, ev = score_text(full_text)
    res.score = s
    res.signals += sig
    res.evidence += ev
    hidden, meta = "", ""
    if path.suffix.lower() == ".pdf":
        hidden, meta = _pdf_hidden_text(path)
    elif path.suffix.lower() == ".docx":
        meta = _docx_metadata(path)
    for label, text in (("hidden_text", hidden), ("metadata", meta)):
        if not text.strip():
            continue
        s2, sig2, ev2 = score_text(text)
        if s2 > 0:
            res.signals += [f"{label}:{x}" for x in sig2]
            res.evidence += ev2
            res.score = min(1.0, res.score + s2 + 0.3)  # concealed payloads are aggravating
        elif label == "hidden_text" and len(text) > 40:
            res.signals.append("hidden_text:present")
            res.score = min(1.0, res.score + 0.2)
    res.flagged = res.score >= THRESHOLD
    return res
