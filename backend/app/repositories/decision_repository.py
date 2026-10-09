"""Safety-decision persistence."""

from __future__ import annotations

from app.db.database import Database
from app.repositories.base import dumps, iso, loads, parse_iso
from app.schemas.safety import CheckResult, SafetyResult


class DecisionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, result: SafetyResult, simulated: bool = False) -> None:
        self.db.execute(
            """
            INSERT OR REPLACE INTO safety_decisions
                (decision_id, proposal_id, approved, reason_code, reason,
                 checks, dispatch_attempted, simulated, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.decision_id,
                result.proposal_id,
                1 if result.approved else 0,
                result.reason_code,
                result.reason,
                dumps(result.check_results and [c.model_dump(mode="json") for c in result.check_results] or result.checks),
                1 if result.dispatch_attempted else 0,
                1 if simulated else 0,
                iso(result.timestamp),
            ),
        )

    def get(self, decision_id: str) -> SafetyResult | None:
        row = self.db.query_one(
            "SELECT * FROM safety_decisions WHERE decision_id = ?", (decision_id,)
        )
        return self._row_to_model(row) if row else None

    def latest(self) -> SafetyResult | None:
        row = self.db.query_one(
            "SELECT * FROM safety_decisions ORDER BY timestamp DESC LIMIT 1"
        )
        return self._row_to_model(row) if row else None

    def list(self, limit: int = 50) -> list[SafetyResult]:
        rows = self.db.query(
            "SELECT * FROM safety_decisions ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row) -> SafetyResult:
        raw = loads(row["checks"], []) or []
        check_results: list[CheckResult] = []
        for item in raw:
            try:
                check_results.append(CheckResult.model_validate(item))
            except Exception:  # pragma: no cover - defensive
                continue
        checks = {c.name: c.status.value for c in check_results}
        return SafetyResult(
            decision_id=row["decision_id"],
            proposal_id=row["proposal_id"],
            approved=bool(row["approved"]),
            reason_code=row["reason_code"],
            reason=row["reason"] or "",
            checks=checks,
            check_results=check_results,
            timestamp=parse_iso(row["timestamp"]),
            dispatch_attempted=bool(row["dispatch_attempted"]),
        )
