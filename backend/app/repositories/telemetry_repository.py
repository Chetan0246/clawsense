"""Telemetry persistence."""

from __future__ import annotations

from app.db.database import Database
from app.repositories.base import iso, parse_iso
from app.schemas.telemetry import SensorReading, SensorStatus


class TelemetryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert_reading(self, device_id: str, reading: SensorReading) -> None:
        self.db.execute(
            """
            INSERT INTO telemetry
                (device_id, sensor, value, unit, status, quality, simulated, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                reading.sensor,
                None if reading.value is None else str(reading.value),
                reading.unit,
                reading.status.value,
                reading.status.value,
                1 if reading.simulated else 0,
                iso(reading.timestamp),
            ),
        )

    def latest(self, device_id: str | None = None) -> list[SensorReading]:
        """Return the most recent reading per sensor."""
        if device_id:
            rows = self.db.query(
                """
                SELECT t.* FROM telemetry t
                JOIN (
                    SELECT sensor, MAX(id) AS max_id FROM telemetry
                    WHERE device_id = ? GROUP BY sensor
                ) m ON t.id = m.max_id
                """,
                (device_id,),
            )
        else:
            rows = self.db.query(
                """
                SELECT t.* FROM telemetry t
                JOIN (
                    SELECT sensor, MAX(id) AS max_id FROM telemetry GROUP BY sensor
                ) m ON t.id = m.max_id
                """
            )
        return [self._row_to_reading(r) for r in rows]

    def history(
        self,
        sensor: str | None = None,
        limit: int = 200,
        since: str | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list = []
        if sensor:
            clauses.append("sensor = ?")
            params.append(sensor)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self.db.query(
            f"SELECT * FROM telemetry {where} ORDER BY id DESC LIMIT ?", params
        )
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_reading(row) -> SensorReading:
        raw = row["value"]
        value: float | int | bool | str | None
        if raw is None:
            value = None
        else:
            try:
                value = float(raw)
                if value.is_integer():
                    value = int(value)
            except (ValueError, TypeError):
                value = raw
        return SensorReading(
            sensor=row["sensor"],
            value=value,
            unit=row["unit"] or "",
            status=SensorStatus(row["status"] or "OK"),
            timestamp=parse_iso(row["timestamp"]),
            simulated=bool(row["simulated"]),
        )

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row["id"],
            "device_id": row["device_id"],
            "sensor": row["sensor"],
            "value": row["value"],
            "unit": row["unit"],
            "status": row["status"],
            "simulated": bool(row["simulated"]),
            "timestamp": row["timestamp"],
        }
