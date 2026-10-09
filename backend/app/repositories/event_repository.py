"""Event persistence with filtering, pagination, and CSV export."""

from __future__ import annotations

import csv
import io

from app.db.database import Database
from app.repositories.base import dumps, iso, loads, parse_iso
from app.schemas.events import EventCategory, EventRecord, EventType, Severity


class EventRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, event: EventRecord) -> None:
        self.db.execute(
            """
            INSERT OR REPLACE INTO events
                (event_id, timestamp, event_type, category, source, severity,
                 device_id, proposal_id, command_id, details, simulated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                iso(event.timestamp),
                event.event_type.value,
                event.category.value,
                event.source,
                event.severity.value,
                event.device_id,
                event.proposal_id,
                event.command_id,
                dumps(event.details),
                1 if event.simulated else 0,
            ),
        )

    def get(self, event_id: str) -> EventRecord | None:
        row = self.db.query_one("SELECT * FROM events WHERE event_id = ?", (event_id,))
        return self._row_to_model(row) if row else None

    def query(
        self,
        *,
        category: str | None = None,
        severity: str | None = None,
        event_type: str | None = None,
        device_id: str | None = None,
        proposal_id: str | None = None,
        command_id: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[EventRecord], int]:
        """Return ``(events, total_count)`` for the given filters."""
        clauses: list[str] = []
        params: list = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        if proposal_id:
            clauses.append("proposal_id = ?")
            params.append(proposal_id)
        if command_id:
            clauses.append("command_id = ?")
            params.append(command_id)
        if search:
            clauses.append(
                "(event_type LIKE ? OR category LIKE ? OR source LIKE ? "
                "OR details LIKE ? OR proposal_id LIKE ? OR command_id LIKE ?)"
            )
            like = f"%{search}%"
            params.extend([like] * 6)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        total_row = self.db.query_one(f"SELECT COUNT(*) AS c FROM events {where}", params)
        total = int(total_row["c"]) if total_row else 0

        rows = self.db.query(
            f"SELECT * FROM events {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [self._row_to_model(r) for r in rows], total

    def export_csv(
        self,
        *,
        category: str | None = None,
        severity: str | None = None,
    ) -> str:
        events, _ = self.query(category=category, severity=severity, limit=100000)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "event_id",
                "timestamp",
                "event_type",
                "category",
                "source",
                "severity",
                "device_id",
                "proposal_id",
                "command_id",
                "simulated",
                "details",
            ]
        )
        for e in events:
            writer.writerow(
                [
                    e.event_id,
                    iso(e.timestamp),
                    e.event_type.value,
                    e.category.value,
                    e.source,
                    e.severity.value,
                    e.device_id or "",
                    e.proposal_id or "",
                    e.command_id or "",
                    e.simulated,
                    dumps(e.details),
                ]
            )
        return buffer.getvalue()

    def count_by_category(self) -> dict[str, int]:
        rows = self.db.query(
            "SELECT category, COUNT(*) AS c FROM events GROUP BY category"
        )
        return {r["category"]: int(r["c"]) for r in rows}

    @staticmethod
    def _row_to_model(row) -> EventRecord:
        return EventRecord(
            event_id=row["event_id"],
            timestamp=parse_iso(row["timestamp"]),
            event_type=EventType(row["event_type"]),
            category=EventCategory(row["category"]),
            source=row["source"],
            severity=Severity(row["severity"]),
            device_id=row["device_id"],
            proposal_id=row["proposal_id"],
            command_id=row["command_id"],
            details=loads(row["details"], {}) or {},
            simulated=bool(row["simulated"]),
        )
