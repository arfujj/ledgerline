"""Content-addressed response cache (SQLite). Makes eval and demo reruns close to free."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


def request_key(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        self._lock = threading.Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT v FROM cache WHERE k = ?", (key,)).fetchone()
        if row is None:
            return None
        value: dict[str, Any] = json.loads(row[0])
        return value

    def put(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (k, v) VALUES (?, ?)", (key, json.dumps(value))
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()
