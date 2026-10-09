"""Audit logging: persist events, feed context memory, broadcast to clients."""

from __future__ import annotations

from datetime import datetime

from app.repositories.event_repository import EventRepository
from app.schemas.events import EventCategory, EventRecord, EventType, Severity
from app.services.context_memory import ContextMemory
from app.services.event_bus import EventBus


class AuditLog:
    """Single entry point for emitting audit events.

    Guarantees that every event is (a) persisted, (b) reflected in context
    memory, and (c) broadcast to connected dashboards — in that order.
    """

    def __init__(
        self,
        repository: EventRepository,
        bus: EventBus,
        context: ContextMemory | None = None,
        *,
        simulated: bool = False,
    ) -> None:
        self.repository = repository
        self.bus = bus
        self.context = context
        self.simulated = simulated

    def record(self, event: EventRecord) -> EventRecord:
        self.repository.insert(event)
        if self.context is not None:
            self.context.add_event(event)
        self.bus.publish(
            {"type": "event", "data": event.model_dump(mode="json")}
        )
        return event

    def emit(
        self,
        event_type: EventType,
        category: EventCategory,
        *,
        source: str = "system",
        severity: Severity = Severity.INFO,
        device_id: str | None = None,
        proposal_id: str | None = None,
        command_id: str | None = None,
        details: dict | None = None,
        timestamp: datetime | None = None,
        simulated: bool | None = None,
    ) -> EventRecord:
        event = EventRecord(
            event_type=event_type,
            category=category,
            source=source,
            severity=severity,
            device_id=device_id,
            proposal_id=proposal_id,
            command_id=command_id,
            details=details or {},
            simulated=self.simulated if simulated is None else simulated,
        )
        if timestamp is not None:
            event.timestamp = timestamp
        return self.record(event)
