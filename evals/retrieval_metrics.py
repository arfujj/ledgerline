"""Retrieval metrics with anchor-based relevance (robust to different chunkings)."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

_WS = re.compile(r"\s+")


def norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


@dataclass(frozen=True)
class Gold:
    doc_id: str
    anchor: str


def is_relevant(doc_id: str, text: str, gold: Gold) -> bool:
    return doc_id == gold.doc_id and norm(gold.anchor) in norm(text)


def relevance_vector(results: Sequence[tuple[str, str]], gold: Sequence[Gold]) -> list[int]:
    """1 if the result at rank i matches any not-yet-matched gold item, else 0."""
    matched: set[int] = set()
    rel: list[int] = []
    for doc_id, text in results:
        hit = 0
        for gi, g in enumerate(gold):
            if gi not in matched and is_relevant(doc_id, text, g):
                matched.add(gi)
                hit = 1
                break
        rel.append(hit)
    return rel


def recall_at_k(rel: list[int], n_gold: int, k: int) -> float:
    return sum(rel[:k]) / n_gold if n_gold else 0.0


def mrr(rel: list[int]) -> float:
    for i, r in enumerate(rel):
        if r:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(rel: list[int], n_gold: int, k: int) -> float:
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rel[:k]))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(n_gold, k)))
    return dcg / ideal if ideal else 0.0
