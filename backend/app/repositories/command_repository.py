"""Command lifecycle persistence."""

from __future__ import annotations

from app.db.database import Database
from app.repositories.base import dumps, iso, loads, parse_iso
from app.schemas.commands import CommandRecord, CommandStatus


class CommandRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, command: CommandRecord) -> None:
        self.db.execute(
            """
            INSERT OR REPLACE INTO commands
                (command_id, proposal_id, decision_id, target_device, action,
                 parameters, status, dispatched_at, acknowledged_at, expires_at,
                 error, simulated, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                command.command_id,
                command.proposal_id,
                command.decision_id,
                command.target_device,
                command.action,
                dumps(command.parameters),
                command.status.value,
                iso(command.dispatched_at),
                iso(command.acknowledged_at),
                iso(command.expires_at),
                command.error,
                1 if command.simulated else 0,
                iso(command.created_at),
            ),
        )

    def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        *,
        acknowledged_at=None,
        error: str | None = None,
    ) -> None:
        self.db.execute(
            """
            UPDATE commands
               SET status = ?, acknowledged_at = COALESCE(?, acknowledged_at),
                   error = COALESCE(?, error)
             WHERE command_id = ?
            """,
            (status.value, iso(acknowledged_at), error, command_id),
        )

    def get(self, command_id: str) -> CommandRecord | None:
        row = self.db.query_one(
            "SELECT * FROM commands WHERE command_id = ?", (command_id,)
        )
        return self._row_to_model(row) if row else None

    def latest(self) -> CommandRecord | None:
        row = self.db.query_one(
            "SELECT * FROM commands ORDER BY created_at DESC LIMIT 1"
        )
        return self._row_to_model(row) if row else None

    def list(self, limit: int = 50) -> list[CommandRecord]:
        rows = self.db.query(
            "SELECT * FROM commands ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [self._row_to_model(r) for r in rows]

    def last_acknowledged(self) -> CommandRecord | None:
        row = self.db.query_one(
            """
            SELECT * FROM commands WHERE status IN ('ACKNOWLEDGED', 'STATE_CONFIRMED')
            ORDER BY created_at DESC LIMIT 1
            """
        )
        return self._row_to_model(row) if row else None

    @staticmethod
    def _row_to_model(row) -> CommandRecord:
        return CommandRecord(
            command_id=row["command_id"],
            proposal_id=row["proposal_id"],
            decision_id=row["decision_id"],
            target_device=row["target_device"],
            action=row["action"],
            parameters=loads(row["parameters"], {}) or {},
            status=CommandStatus(row["status"]),
            dispatched_at=parse_iso(row["dispatched_at"]),
            acknowledged_at=parse_iso(row["acknowledged_at"]),
            expires_at=parse_iso(row["expires_at"]),
            error=row["error"],
            simulated=bool(row["simulated"]),
            created_at=parse_iso(row["created_at"]),
        )
