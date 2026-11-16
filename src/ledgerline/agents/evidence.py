"""Evidence items: the only things an answer or deliverable sentence may cite."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EvidenceKind = Literal["doc", "query", "assumption", "finding", "computation"]


class Evidence(BaseModel):
    eid: str = ""  # assigned by EvidencePool (E1, E2, ...)
    kind: EvidenceKind
    text: str
    cites: list[str]  # canonical citation strings, e.g. [doc:X#s4(a)(3)], [q:q_ab12]
    trusted: bool = True
    meta: dict[str, str] = Field(default_factory=dict)


class EvidencePool:
    def __init__(self) -> None:
        self.items: list[Evidence] = []
        self._by_key: dict[str, Evidence] = {}

    def add(self, ev: Evidence) -> Evidence:
        key = "|".join(ev.cites) + "|" + ev.text[:80]
        if key in self._by_key:
            return self._by_key[key]
        ev = ev.model_copy(update={"eid": f"E{len(self.items) + 1}"})
        self.items.append(ev)
        self._by_key[key] = ev
        return ev

    def get(self, eid: str) -> Evidence | None:
        return next((e for e in self.items if e.eid == eid), None)

    def render(self, max_chars: int = 900) -> str:
        """Evidence block for prompts. Untrusted text is fenced and labelled as data."""
        out = []
        for e in self.items:
            tag = "" if e.trusted else ' untrusted="true"'
            out.append(
                f'<evidence id="{e.eid}" cites="{" ".join(e.cites)}"{tag}>\n'
                f"{e.text[:max_chars]}\n</evidence>"
            )
        return "\n".join(out)
