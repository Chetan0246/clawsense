"""State-transition persistence."""

from __future__ import annotations

from app.db.database import Database
from app.repositories.base import dumps, iso, loads, parse_iso
from app.schemas.system import StateTransition, SystemState


class TransitionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, transition: StateTransition) -> None:
        self.db.execute(
            """
            INSERT OR REPLACE INTO state_transitions
                (transition_id, previous_state, new_state, reason_code, reason,
                 diagnostics, simulated, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transition.transition_id,
                transition.previous_state.value if transition.previous_state else None,
                transition.new_state.value,
                transition.reason_code,
                transition.reason,
                dumps(transition.diagnostics),
                1 if transition.simulated else 0,
                iso(transition.timestamp),
            ),
        )

    def list(self, limit: int = 50) -> list[StateTransition]:
        rows = self.db.query(
            "SELECT * FROM state_transitions ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        return [self._row_to_model(r) for r in rows]

    def latest(self) -> StateTransition | None:
        row = self.db.query_one(
            "SELECT * FROM state_transitions ORDER BY timestamp DESC LIMIT 1"
        )
        return self._row_to_model(row) if row else None

    @staticmethod
    def _row_to_model(row) -> StateTransition:
        prev = row["previous_state"]
        return StateTransition(
            transition_id=row["transition_id"],
            previous_state=SystemState(prev) if prev else None,
            new_state=SystemState(row["new_state"]),
            reason_code=row["reason_code"],
            reason=row["reason"] or "",
            timestamp=parse_iso(row["timestamp"]),
            simulated=bool(row["simulated"]),
            diagnostics=loads(row["diagnostics"], {}) or {},
        )
