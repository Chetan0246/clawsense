"""Event schemas (PLAN.md sections 7 & 16)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventCategory(str, Enum):
    SENSOR_READING = "sensor_reading"
    SENSOR_THRESHOLD = "sensor_threshold"
    CONTEXT_UPDATE = "context_update"
    AGENT_PROPOSAL = "agent_proposal"
    SAFETY_APPROVAL = "safety_approval"
    SAFETY_REJECTION = "safety_rejection"
    COMMAND_DISPATCH = "command_dispatch"
    DEVICE_ACK = "device_ack"
    DEVICE_FAILURE = "device_failure"
    AGENT_TIMEOUT = "agent_timeout"
    STATE_TRANSITION = "state_transition"
    OFFLINE_FALLBACK = "offline_fallback"
    RECOVERY = "recovery"
    MANUAL_OVERRIDE = "manual_override"
    CONFIG_CHANGE = "config_change"


class EventType(str, Enum):
    TEMPERATURE_UPDATED = "TEMPERATURE_UPDATED"
    HUMIDITY_UPDATED = "HUMIDITY_UPDATED"
    MOTION_DETECTED = "MOTION_DETECTED"
    MOTION_CLEARED = "MOTION_CLEARED"
    THIRD_SENSOR_UPDATED = "THIRD_SENSOR_UPDATED"
    THRESHOLD_EXCEEDED = "THRESHOLD_EXCEEDED"
    AGENT_PROPOSAL = "AGENT_PROPOSAL"
    ACTION_APPROVED = "ACTION_APPROVED"
    ACTION_REJECTED = "ACTION_REJECTED"
    COMMAND_DISPATCHED = "COMMAND_DISPATCHED"
    COMMAND_ACKNOWLEDGED = "COMMAND_ACKNOWLEDGED"
    DEVICE_FAILURE = "DEVICE_FAILURE"
    DEVICE_TIMEOUT = "DEVICE_TIMEOUT"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    STATE_TRANSITION = "STATE_TRANSITION"
    FALLBACK_ACTIVATED = "FALLBACK_ACTIVATED"
    FALLBACK_ACTION = "FALLBACK_ACTION"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class Severity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventRecord(BaseModel):
    """An append-oriented audit event.

    Secrets must never be placed in ``details``.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=_utcnow)
    event_type: EventType
    category: EventCategory
    source: str = "system"
    severity: Severity = Severity.INFO
    device_id: str | None = None
    proposal_id: str | None = None
    command_id: str | None = None
    details: dict = Field(default_factory=dict)
    simulated: bool = False
