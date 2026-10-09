"""SQLite persistence layer.

Uses the standard library ``sqlite3`` module behind a small repository
abstraction (explicitly permitted by PLAN.md section 16) so there are no
compiled dependencies and behaviour is fully deterministic.

The schema is initialised idempotently on startup.  Safety decisions and
command results are persisted independently so an application restart does not
silently erase history.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id           TEXT PRIMARY KEY,
    device_type         TEXT NOT NULL,
    firmware_version    TEXT,
    last_seen           TEXT,
    connectivity_status TEXT,
    simulated           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS telemetry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   TEXT NOT NULL,
    sensor      TEXT NOT NULL,
    value       TEXT,
    unit        TEXT,
    status      TEXT,
    quality     TEXT,
    simulated   INTEGER NOT NULL DEFAULT 0,
    timestamp   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(timestamp);
CREATE INDEX IF NOT EXISTS idx_telemetry_sensor ON telemetry(sensor);

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    action      TEXT NOT NULL,
    parameters  TEXT NOT NULL,
    reason      TEXT,
    context_ref TEXT,
    simulated   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_proposals_created ON proposals(created_at);

CREATE TABLE IF NOT EXISTS safety_decisions (
    decision_id   TEXT PRIMARY KEY,
    proposal_id   TEXT NOT NULL,
    approved      INTEGER NOT NULL,
    reason_code   TEXT NOT NULL,
    reason        TEXT,
    checks        TEXT NOT NULL,
    dispatch_attempted INTEGER NOT NULL DEFAULT 0,
    simulated     INTEGER NOT NULL DEFAULT 0,
    timestamp     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_proposal ON safety_decisions(proposal_id);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON safety_decisions(timestamp);

CREATE TABLE IF NOT EXISTS commands (
    command_id     TEXT PRIMARY KEY,
    proposal_id    TEXT NOT NULL,
    decision_id    TEXT NOT NULL,
    target_device  TEXT NOT NULL,
    action         TEXT NOT NULL,
    parameters     TEXT NOT NULL,
    status         TEXT NOT NULL,
    dispatched_at  TEXT,
    acknowledged_at TEXT,
    expires_at     TEXT,
    error          TEXT,
    simulated      INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_commands_proposal ON commands(proposal_id);
CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);

CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,
    timestamp    TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    category     TEXT NOT NULL,
    source       TEXT NOT NULL,
    severity     TEXT NOT NULL,
    device_id    TEXT,
    proposal_id  TEXT,
    command_id   TEXT,
    details      TEXT NOT NULL,
    simulated    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_device ON events(device_id);
CREATE INDEX IF NOT EXISTS idx_events_proposal ON events(proposal_id);
CREATE INDEX IF NOT EXISTS idx_events_command ON events(command_id);

CREATE TABLE IF NOT EXISTS state_transitions (
    transition_id TEXT PRIMARY KEY,
    previous_state TEXT,
    new_state     TEXT NOT NULL,
    reason_code   TEXT NOT NULL,
    reason        TEXT,
    diagnostics   TEXT NOT NULL,
    simulated     INTEGER NOT NULL DEFAULT 0,
    timestamp     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transitions_ts ON state_transitions(timestamp);
"""


class Database:
    """A tiny thread-safe SQLite wrapper.

    A single connection guarded by a re-entrant lock is sufficient for the
    local single-process demonstration workload and avoids connection-pool
    complexity that the project explicitly does not need.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")

    def initialize(self) -> None:
        """Create tables and indexes if they do not already exist, then migrate."""
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Apply predictable, additive schema migrations.

        SQLite's ``CREATE TABLE IF NOT EXISTS`` never alters an existing table,
        so new nullable columns must be added explicitly. This keeps an existing
        database usable across upgrades without a migration framework.
        """
        migrations: dict[str, list[tuple[str, str]]] = {
            "commands": [("expires_at", "TEXT")],
        }
        for table, columns in migrations.items():
            existing = {
                row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")
            }
            for name, ddl_type in columns:
                if name not in existing:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"
                    )

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, seq)
            self._conn.commit()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.fetchall()

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.fetchone()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
