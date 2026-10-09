"""System state machine schemas (PLAN.md section 11)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SystemState(str, Enum):
    ONLINE_AGENT = "ONLINE_AGENT"
    DEGRADED = "DEGRADED"
    OFFLINE_LOCAL = "OFFLINE_LOCAL"
    RECOVERY = "RECOVERY"
    SAFE_LOCKDOWN = "SAFE_LOCKDOWN"


class StateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transition_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    previous_state: SystemState | None = None
    new_state: SystemState
    reason_code: str
    reason: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)
    simulated: bool = False
    diagnostics: dict = Field(default_factory=dict)


class SystemStatus(BaseModel):
    """Aggregated system status surfaced to the dashboard."""

    model_config = ConfigDict(extra="forbid")

    current_state: SystemState
    previous_state: SystemState | None = None
    transition_reason_code: str | None = None
    transition_reason: str | None = None
    last_transition_at: datetime | None = None
    controller_authority: str = "agent"  # agent | local | none
    agent_available: bool = False
    agent_provider: str = "simulated"
    network_available: bool = True
    device_connected: bool = False
    last_successful_agent_request: datetime | None = None
    last_successful_device_communication: datetime | None = None
    recovery_status: str = "idle"
    simulated: bool = False
    uptime_seconds: float = 0.0
