"""Device registry persistence."""

from __future__ import annotations

from app.db.database import Database
from app.repositories.base import iso


class DeviceRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert(
        self,
        device_id: str,
        device_type: str = "esp32s3",
        firmware_version: str | None = None,
        connectivity_status: str = "unknown",
        simulated: bool = False,
        last_seen=None,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO devices
                (device_id, device_type, firmware_version, last_seen,
                 connectivity_status, simulated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                device_type = excluded.device_type,
                firmware_version = COALESCE(excluded.firmware_version, devices.firmware_version),
                last_seen = COALESCE(excluded.last_seen, devices.last_seen),
                connectivity_status = excluded.connectivity_status,
                simulated = excluded.simulated
            """,
            (
                device_id,
                device_type,
                firmware_version,
                iso(last_seen),
                connectivity_status,
                1 if simulated else 0,
            ),
        )

    def get(self, device_id: str) -> dict | None:
        row = self.db.query_one(
            "SELECT * FROM devices WHERE device_id = ?", (device_id,)
        )
        if not row:
            return None
        return {
            "device_id": row["device_id"],
            "device_type": row["device_type"],
            "firmware_version": row["firmware_version"],
            "last_seen": row["last_seen"],
            "connectivity_status": row["connectivity_status"],
            "simulated": bool(row["simulated"]),
        }

    def list(self) -> list[dict]:
        rows = self.db.query("SELECT * FROM devices")
        return [
            {
                "device_id": r["device_id"],
                "device_type": r["device_type"],
                "firmware_version": r["firmware_version"],
                "last_seen": r["last_seen"],
                "connectivity_status": r["connectivity_status"],
                "simulated": bool(r["simulated"]),
            }
            for r in rows
        ]
