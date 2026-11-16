"""Local (CPU) embedding and reranking via FastEmbed, with an on-disk embedding cache.

Zero API cost. Embeddings are cached by (model, sha256(text)) so re-indexing is near-instant.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
DENSE_DIM = 384
SPARSE_MODEL = "Qdrant/bm25"
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
CACHE_PATH = Path(os.environ.get("LEDGERLINE_EMBED_CACHE", "data/cache/embeddings.sqlite"))


class _Cache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v BLOB)")
        self.lock = threading.Lock()

    def get_many(self, keys: list[str]) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        with self.lock:
            for i in range(0, len(keys), 500):
                part = keys[i : i + 500]
                q = f"SELECT k, v FROM emb WHERE k IN ({','.join('?' * len(part))})"  # noqa: S608
                out.update(dict(self.conn.execute(q, part).fetchall()))
        return out

    def put_many(self, items: dict[str, bytes]) -> None:
        with self.lock:
            self.conn.executemany("INSERT OR REPLACE INTO emb VALUES (?, ?)", items.items())
            self.conn.commit()


@lru_cache(maxsize=1)
def _cache() -> _Cache:
    return _Cache(CACHE_PATH)


def _key(model: str, text: str) -> str:
    return model + ":" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def dense() -> Any:
    from fastembed import TextEmbedding

    return TextEmbedding(DENSE_MODEL)


@lru_cache(maxsize=1)
def sparse() -> Any:
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(SPARSE_MODEL)


@lru_cache(maxsize=1)
def reranker() -> Any:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(RERANK_MODEL)


def _parallel() -> int | None:
    return 0 if (os.cpu_count() or 1) > 2 else None  # 0 = all cores (fastembed)


def embed_dense(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    keys = [_key(DENSE_MODEL, t) for t in texts]
    hit = _cache().get_many(keys)
    missing = [i for i, k in enumerate(keys) if k not in hit]
    if missing:
        vecs = list(
            dense().embed(
                [texts[i] for i in missing],
                batch_size=batch_size,
                parallel=_parallel() if len(missing) > 256 else None,
            )
        )
        new = {
            keys[i]: np.asarray(v, dtype=np.float32).tobytes()
            for i, v in zip(missing, vecs, strict=True)
        }
        _cache().put_many(new)
        hit.update(new)
    return [np.frombuffer(hit[k], dtype=np.float32).tolist() for k in keys]


def embed_dense_query(text: str) -> list[float]:
    return list(next(iter(dense().query_embed(text))).tolist())


def embed_sparse(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    keys = [_key(SPARSE_MODEL, t) for t in texts]
    hit = _cache().get_many(keys)
    missing = [i for i, k in enumerate(keys) if k not in hit]
    if missing:
        embs = list(sparse().embed([texts[i] for i in missing]))
        new = {
            keys[i]: json.dumps([e.indices.tolist(), e.values.tolist()]).encode()
            for i, e in zip(missing, embs, strict=True)
        }
        _cache().put_many(new)
        hit.update(new)
    out: list[tuple[list[int], list[float]]] = []
    for k in keys:
        idx, val = json.loads(hit[k])
        out.append((idx, val))
    return out


def embed_sparse_query(text: str) -> tuple[list[int], list[float]]:
    e = next(iter(sparse().query_embed(text)))
    return e.indices.tolist(), e.values.tolist()


def rerank_scores(query: str, docs: list[str]) -> list[float]:
    return [float(s) for s in reranker().rerank(query, docs)]
