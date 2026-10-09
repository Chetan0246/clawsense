"""Bounded contextual memory (PLAN.md section 13).

Holds a bounded rolling buffer of recent events and the latest telemetry
snapshot.  The agent receives a concise summary rather than an unlimited raw
event stream.  Also tracks recently executed actions so the safety supervisor
can enforce cooldowns and detect duplicates deterministically.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.schemas.events import EventRecord
from app.schemas.telemetry import SensorReading, SensorStatus, TelemetrySnapshot

MAX_EVENTS = 100
MAX_ACTIONS = 50


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RecentAction:
    """A previously dispatched/executed action, for cooldown + duplicate checks."""

    action: str
    parameters: dict
    timestamp: datetime
    command_id: str | None = None
    proposal_id: str | None = None


@dataclass
class ContextMemory:
    """A bounded in-memory context buffer.

    The backend mirror of the ESP32's on-device bounded buffer.
    """

    events: deque[EventRecord] = field(default_factory=lambda: deque(maxlen=MAX_EVENTS))
    actions: deque[RecentAction] = field(
        default_factory=lambda: deque(maxlen=MAX_ACTIONS)
    )
    telemetry: TelemetrySnapshot | None = None

    # -- updates -----------------------------------------------------------
    def update_telemetry(self, snapshot: TelemetrySnapshot) -> None:
        self.telemetry = snapshot

    def add_event(self, event: EventRecord) -> None:
        self.events.append(event)

    def record_action(
        self,
        action: str,
        parameters: dict,
        *,
        timestamp: datetime | None = None,
        command_id: str | None = None,
        proposal_id: str | None = None,
    ) -> None:
        self.actions.append(
            RecentAction(
                action=action,
                parameters=dict(parameters),
                timestamp=timestamp or _utcnow(),
                command_id=command_id,
                proposal_id=proposal_id,
            )
        )

    # -- queries -----------------------------------------------------------
    def telemetry_age_seconds(self, now: datetime | None = None) -> float | None:
        if self.telemetry is None or self.telemetry.timestamp is None:
            return None
        now = now or _utcnow()
        ts = self.telemetry.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (now - ts).total_seconds())

    def recent_actions(
        self, window_seconds: float, now: datetime | None = None
    ) -> list[RecentAction]:
        now = now or _utcnow()
        cutoff = now.timestamp() - window_seconds
        return [a for a in self.actions if a.timestamp.timestamp() >= cutoff]

    def last_action_time(
        self, action: str, now: datetime | None = None
    ) -> datetime | None:
        matches = [a for a in self.actions if a.action == action]
        if not matches:
            return None
        return max(a.timestamp for a in matches)

    def find_duplicate(
        self,
        action: str,
        parameters: dict,
        window_seconds: float,
        now: datetime | None = None,
    ) -> RecentAction | None:
        for a in reversed(self.recent_actions(window_seconds, now=now)):
            if a.action == action and a.parameters == parameters:
                return a
        return None

    def clear(self) -> None:
        self.events.clear()
        self.actions.clear()
        self.telemetry = None

    # -- agent-facing summary ---------------------------------------------
    def summary(self, recent_event_limit: int = 10) -> dict[str, Any]:
        """A concise, bounded context summary for the agent.

        Deliberately excludes credentials and unnecessary personal data.
        """
        latest: dict[str, Any] = {}
        stale: list[str] = []
        if self.telemetry is not None:
            for name, reading in self.telemetry.readings.items():
                latest[name] = {
                    "value": reading.value,
                    "unit": reading.unit,
                    "status": reading.status.value,
                    "simulated": reading.simulated,
                }
                if reading.status == SensorStatus.STALE:
                    stale.append(name)
        recent = [
            {
                "event_type": e.event_type.value,
                "category": e.category.value,
                "severity": e.severity.value,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in list(self.events)[-recent_event_limit:]
        ]
        return {
            "latest_readings": latest,
            "stale_sensors": stale,
            "telemetry_age_seconds": self.telemetry_age_seconds(),
            "recent_events": recent,
            "simulated": bool(self.telemetry and self.telemetry.simulated),
        }

    def reading(self, sensor: str) -> SensorReading | None:
        if self.telemetry is None:
            return None
        return self.telemetry.readings.get(sensor)
