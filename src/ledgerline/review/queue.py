"""Human-in-the-loop review queue (SQLAlchemy: Postgres in compose, SQLite in tests).

Every finding of an engagement is queued as `pending`. A reviewer can accept, edit or reject
it; every action is appended to `review_log` with before/after snapshots. Exports apply the
decisions: rejected findings are excluded and edits replace the drafted text.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

Action = Literal["accept", "edit", "reject", "reset"]
EDITABLE = {"title", "severity", "rationale", "recommendation", "owner"}


class Base(DeclarativeBase):
    pass


class ReviewItem(Base):
    __tablename__ = "review_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    finding_id: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewLog(Base):
    __tablename__ = "review_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    finding_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))
    reviewer: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text, default="")
    before: Mapped[dict[str, Any]] = mapped_column(JSON)
    after: Mapped[dict[str, Any]] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class ReviewQueue:
    def __init__(self, dsn: str) -> None:
        self.engine: Engine = create_engine(dsn, future=True)
        Base.metadata.create_all(self.engine)

    def enqueue(self, run_id: str, findings: list[dict[str, Any]]) -> int:
        with Session(self.engine) as s:
            existing = set(
                s.scalars(select(ReviewItem.finding_id).where(ReviewItem.run_id == run_id))
            )
            n = 0
            for f in findings:
                if f["finding_id"] in existing:
                    continue
                s.add(
                    ReviewItem(
                        run_id=run_id,
                        finding_id=f["finding_id"],
                        category=f["category"],
                        payload=json.loads(json.dumps(f)),
                        status="pending",
                        updated_at=_now(),
                    )
                )
                n += 1
            s.commit()
        return n

    def items(self, run_id: str, status: str | None = None) -> list[dict[str, Any]]:
        with Session(self.engine) as s:
            q = select(ReviewItem).where(ReviewItem.run_id == run_id)
            if status:
                q = q.where(ReviewItem.status == status)
            return [
                {
                    "finding_id": i.finding_id,
                    "category": i.category,
                    "status": i.status,
                    "reviewer": i.reviewer,
                    "updated_at": i.updated_at.isoformat(),
                    **{"finding": i.payload},
                }
                for i in s.scalars(q.order_by(ReviewItem.id))
            ]

    def act(
        self,
        run_id: str,
        finding_id: str,
        action: Action,
        reviewer: str,
        edits: dict[str, Any] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        if not reviewer.strip():
            raise ReviewError("reviewer is required")
        with Session(self.engine) as s:
            item = s.scalars(
                select(ReviewItem).where(
                    ReviewItem.run_id == run_id, ReviewItem.finding_id == finding_id
                )
            ).one_or_none()
            if item is None:
                raise ReviewError(f"unknown finding {finding_id} in run {run_id}")
            before = {"status": item.status, **item.payload}
            payload = dict(item.payload)
            if action == "edit":
                bad = set(edits or {}) - EDITABLE
                if not edits or bad:
                    raise ReviewError(f"edits must be a non-empty subset of {sorted(EDITABLE)}")
                if "severity" in edits and edits["severity"] not in (
                    "critical",
                    "high",
                    "medium",
                    "low",
                ):
                    raise ReviewError("invalid severity")
                payload.update(edits)
                payload["edited"] = True
                item.payload = payload
                item.status = "edited"
            elif action == "accept":
                item.status = "accepted"
            elif action == "reject":
                item.status = "rejected"
            elif action == "reset":
                item.status = "pending"
            else:
                raise ReviewError(f"unknown action {action}")
            item.reviewer = reviewer
            item.updated_at = _now()
            s.add(
                ReviewLog(
                    run_id=run_id,
                    finding_id=finding_id,
                    action=action,
                    reviewer=reviewer,
                    reason=reason,
                    before=before,
                    after={"status": item.status, **payload},
                    ts=_now(),
                )
            )
            s.commit()
            return {"finding_id": finding_id, "status": item.status}

    def log(self, run_id: str) -> list[dict[str, Any]]:
        with Session(self.engine) as s:
            return [
                {
                    "finding_id": r.finding_id,
                    "action": r.action,
                    "reviewer": r.reviewer,
                    "reason": r.reason,
                    "ts": r.ts.isoformat(),
                    "before": r.before,
                    "after": r.after,
                }
                for r in s.scalars(
                    select(ReviewLog).where(ReviewLog.run_id == run_id).order_by(ReviewLog.id)
                )
            ]

    def reviewed_findings(self, run_id: str) -> list[dict[str, Any]]:
        """Findings for export: rejected removed, edits applied, review status attached."""
        out = []
        for i in self.items(run_id):
            if i["status"] == "rejected":
                continue
            out.append({**i["finding"], "review_status": i["status"]})
        return out

    def summary(self, run_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for i in self.items(run_id):
            counts[i["status"]] = counts.get(i["status"], 0) + 1
        return counts
