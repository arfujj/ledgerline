"""Hard spend caps. A run stops with BudgetExceeded rather than silently overspending."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path


class BudgetExceeded(RuntimeError):
    pass


class SpendTracker:
    """Tracks spend per run (in memory) and per UTC day (persisted to a small JSON file)."""

    def __init__(self, max_per_run: float, max_per_day: float, ledger_path: Path | None) -> None:
        self.max_per_run = max_per_run
        self.max_per_day = max_per_day
        self.ledger_path = ledger_path
        self._run_spend: dict[str, float] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _load_day(self) -> dict[str, float]:
        if self.ledger_path is None or not self.ledger_path.exists():
            return {}
        with self._lock:
            raw = self.ledger_path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        data: dict[str, float] = json.loads(raw)
        return data

    def day_spend(self) -> float:
        return self._load_day().get(self._today(), 0.0)

    def run_spend(self, run_id: str) -> float:
        return self._run_spend.get(run_id, 0.0)

    def check(self, run_id: str, estimate_usd: float = 0.0) -> None:
        """Raise if spending `estimate_usd` more would breach a cap."""
        if self.run_spend(run_id) + estimate_usd > self.max_per_run:
            raise BudgetExceeded(
                f"Run {run_id}: ${self.run_spend(run_id):.4f} spent, cap ${self.max_per_run:.2f}"
            )
        if self.day_spend() + estimate_usd > self.max_per_day:
            raise BudgetExceeded(
                f"Daily spend ${self.day_spend():.4f}, cap ${self.max_per_day:.2f}"
            )

    def record(self, run_id: str, usd: float) -> None:
        with self._lock:
            self._run_spend[run_id] = self.run_spend(run_id) + usd
            if self.ledger_path is not None:
                day = self._load_day()
                today = self._today()
                day[today] = day.get(today, 0.0) + usd
                self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
                # Atomic replace so concurrent readers never see a partially written file.
                tmp = self.ledger_path.with_suffix(f".{threading.get_ident()}.tmp")
                tmp.write_text(json.dumps(day, sort_keys=True), encoding="utf-8")
                tmp.replace(self.ledger_path)
