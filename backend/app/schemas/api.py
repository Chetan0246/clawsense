"""API request models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.telemetry import SensorStatus
from app.simulation.device import Scenario
from app.transports.simulated import FailureMode


class ProposalRequest(BaseModel):
    """Manual / operator proposal.  Always goes through safety validation."""

    model_config = ConfigDict(extra="forbid")

    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class RawValidateRequest(BaseModel):
    """Raw payload submitted to the safety supervisor for dry-run validation."""

    model_config = ConfigDict(extra="allow")

    action: str | None = None
    parameters: dict[str, Any] | None = None
    reason: str | None = None
    proposal_id: str | None = None
    source: str | None = None


class ForceStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    reason_code: str = "MANUAL_OVERRIDE"
    reason: str = ""


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: Scenario


class AgentModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str


class AgentAvailabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool


class FailureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: FailureMode


class SensorReadingInput(BaseModel):
    """A single sensor reading pushed by a device."""

    model_config = ConfigDict(extra="forbid")

    value: float | int | bool | str | None = None
    unit: str = ""
    status: SensorStatus = SensorStatus.OK
    timestamp: datetime | None = None
    detail: str = ""


class TelemetryIngestRequest(BaseModel):
    """Telemetry pushed from a device (used in hardware mode or by tests)."""

    model_config = ConfigDict(extra="forbid")

    device_id: str
    timestamp: datetime | None = None
    simulated: bool = False
    readings: dict[str, SensorReadingInput] = Field(default_factory=dict)
