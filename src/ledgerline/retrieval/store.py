"""Qdrant collections and hybrid search (dense + BM25, RRF fusion, optional rerank)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from qdrant_client import QdrantClient, models

from ledgerline.ingest.models import Chunk
from ledgerline.retrieval import embeddings as emb

Mode = Literal["dense", "hybrid"]


@dataclass
class Hit:
    chunk: Chunk
    score: float


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class ChunkStore:
    def __init__(self, client: QdrantClient, collection: str) -> None:
        self.client = client
        self.collection = collection

    def recreate(self, with_sparse: bool = True) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config={
                "dense": models.VectorParams(size=emb.DENSE_DIM, distance=models.Distance.COSINE)
            },
            sparse_vectors_config=(
                {"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)}
                if with_sparse
                else None
            ),
        )
        for field, schema in (
            ("doc_id", models.PayloadSchemaType.KEYWORD),
            ("corpus", models.PayloadSchemaType.KEYWORD),
            ("lineage_id", models.PayloadSchemaType.KEYWORD),
            ("trusted", models.PayloadSchemaType.BOOL),
        ):
            self.client.create_payload_index(self.collection, field, schema)

    def upsert(
        self,
        chunks: list[Chunk],
        use_header: bool = True,
        with_sparse: bool = True,
        batch: int = 1024,
    ) -> None:
        for i in range(0, len(chunks), batch):
            part = chunks[i : i + batch]
            texts = [c.embed_text if use_header else c.text for c in part]
            dense = emb.embed_dense(texts)
            sparse = emb.embed_sparse(texts) if with_sparse else [None] * len(part)
            points = []
            for c, d, s in zip(part, dense, sparse, strict=True):
                vec: dict[str, Any] = {"dense": d}
                if s is not None:
                    vec["bm25"] = models.SparseVector(indices=s[0], values=s[1])
                payload = c.model_dump(mode="json")
                points.append(
                    models.PointStruct(id=_point_id(c.chunk_id), vector=vec, payload=payload)
                )
            self.client.upsert(self.collection, points=points)

    def count(self) -> int:
        return self.client.count(self.collection).count

    def search(
        self,
        query: str,
        k: int = 10,
        mode: Mode = "hybrid",
        rerank: bool = False,
        corpus: str | None = None,
        doc_ids: list[str] | None = None,
        as_of: date | None = None,
        candidates: int = 50,
    ) -> list[Hit]:
        flt = build_filter(corpus=corpus, doc_ids=doc_ids, as_of=as_of)
        limit = max(candidates, k) if rerank else k
        dq = emb.embed_dense_query(query)
        if mode == "dense":
            res = self.client.query_points(
                self.collection,
                query=dq,
                using="dense",
                limit=limit,
                query_filter=flt,
                with_payload=True,
            )
        else:
            si, sv = emb.embed_sparse_query(query)
            res = self.client.query_points(
                self.collection,
                prefetch=[
                    models.Prefetch(query=dq, using="dense", limit=limit, filter=flt),
                    models.Prefetch(
                        query=models.SparseVector(indices=si, values=sv),
                        using="bm25",
                        limit=limit,
                        filter=flt,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                with_payload=True,
            )
        hits = [Hit(Chunk.model_validate(p.payload), p.score) for p in res.points]
        if rerank and hits:
            scores = emb.rerank_scores(query, [h.chunk.embed_text for h in hits])
            hits = [Hit(h.chunk, s) for h, s in zip(hits, scores, strict=True)]
            hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]


def build_filter(
    corpus: str | None = None, doc_ids: list[str] | None = None, as_of: date | None = None
) -> models.Filter | None:
    must: list[Any] = []
    if corpus:
        must.append(models.FieldCondition(key="corpus", match=models.MatchValue(value=corpus)))
    if doc_ids:
        must.append(models.FieldCondition(key="doc_id", match=models.MatchAny(any=doc_ids)))
    if as_of is not None:
        iso = as_of.isoformat()
        # Version visible on as_of: valid_from <= as_of AND (valid_to is null OR valid_to > as_of)
        must.append(
            models.Filter(
                should=[
                    models.IsNullCondition(is_null=models.PayloadField(key="valid_from")),
                    models.FieldCondition(key="valid_from", range=models.DatetimeRange(lte=iso)),
                ]
            )
        )
        must.append(
            models.Filter(
                should=[
                    models.IsNullCondition(is_null=models.PayloadField(key="valid_to")),
                    models.FieldCondition(key="valid_to", range=models.DatetimeRange(gt=iso)),
                ]
            )
        )
    return models.Filter(must=must) if must else None
