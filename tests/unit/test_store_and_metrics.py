from __future__ import annotations

import hashlib
from datetime import date

import pytest
from evals.retrieval_metrics import Gold, mrr, ndcg_at_k, recall_at_k, relevance_vector
from qdrant_client import QdrantClient

from ledgerline.ingest.models import Chunk
from ledgerline.retrieval import embeddings as emb
from ledgerline.retrieval import store as store_mod
from ledgerline.retrieval.store import ChunkStore, build_filter

VOCAB = ["reserve", "rehypothecate", "dispute", "credit", "retention", "kyc", "freeze", "audit"]


def _vec(text: str) -> list[float]:
    t = text.lower()
    v = [float(t.count(w)) for w in VOCAB] + [0.0] * (emb.DENSE_DIM - len(VOCAB))
    v[-1] = 0.01
    return v


def _sparse(text: str) -> tuple[list[int], list[float]]:
    idx = sorted({int(hashlib.md5(w.encode()).hexdigest()[:6], 16) for w in text.lower().split()})
    return idx, [1.0] * len(idx)


@pytest.fixture
def fake_emb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        store_mod.emb, "embed_dense", lambda ts, batch_size=64: [_vec(t) for t in ts]
    )
    monkeypatch.setattr(store_mod.emb, "embed_dense_query", _vec)
    monkeypatch.setattr(store_mod.emb, "embed_sparse", lambda ts: [_sparse(t) for t in ts])
    monkeypatch.setattr(store_mod.emb, "embed_sparse_query", _sparse)
    monkeypatch.setattr(
        store_mod.emb,
        "rerank_scores",
        lambda q, ds: [float(sum(d.lower().count(w) for w in q.lower().split())) for d in ds],
    )


def _c(
    i: str, text: str, vf: date | None = None, vt: date | None = None, corpus: str = "regulatory"
) -> Chunk:
    return Chunk(
        chunk_id=i,
        doc_id=i.split("::")[0],
        corpus=corpus,
        doc_type="x",
        title="t",
        issuer="i",
        text=text,
        header="[h]",
        valid_from=vf,
        valid_to=vt,
    )  # type: ignore[arg-type]


def test_hybrid_search_filters_and_rerank(fake_emb: None) -> None:
    s = ChunkStore(QdrantClient(":memory:"), "t")
    s.recreate()
    s.upsert(
        [
            _c("P::0", "reserve rehypothecate proposed", date(2026, 3, 2), date(2026, 10, 23)),
            _c("F::0", "reserve rehypothecate final rehypothecate", date(2026, 10, 23)),
            _c("D::0", "dispute credit retention", corpus="dataroom"),
        ]
    )
    assert s.count() == 3
    hits = s.search("rehypothecate reserve", k=2)
    assert {h.chunk.doc_id for h in hits} == {"P", "F"}
    june = s.search("rehypothecate reserve", k=3, as_of=date(2026, 6, 1), corpus="regulatory")
    assert [h.chunk.doc_id for h in june] == ["P"]
    nov = s.search("rehypothecate reserve", k=3, as_of=date(2026, 11, 16), corpus="regulatory")
    assert [h.chunk.doc_id for h in nov] == ["F"]
    rr = s.search("rehypothecate", k=1, rerank=True)
    assert rr[0].chunk.doc_id == "F"
    dense = s.search("dispute credit", k=1, mode="dense")
    assert dense[0].chunk.doc_id == "D"
    only = s.search("reserve", k=5, doc_ids=["D"])
    assert [h.chunk.doc_id for h in only] == ["D"]
    s.recreate(with_sparse=False)
    assert s.count() == 0


def test_build_filter_none() -> None:
    assert build_filter() is None


def test_retrieval_metrics() -> None:
    gold = [Gold("A", "needle text"), Gold("B", "other")]
    res = [("C", "x"), ("A", "has Needle   text here"), ("B", "other thing"), ("A", "needle text")]
    rel = relevance_vector(res, gold)
    assert rel == [0, 1, 1, 0]
    assert recall_at_k(rel, 2, 2) == 0.5
    assert recall_at_k(rel, 2, 3) == 1.0
    assert mrr(rel) == 0.5
    assert 0 < ndcg_at_k(rel, 2, 10) < 1
    assert mrr([0, 0]) == 0.0
    assert recall_at_k([], 0, 5) == 0.0
