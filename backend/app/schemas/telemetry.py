"""Telemetry schemas (PLAN.md section 16).

Sensor readings explicitly carry a *quality* flag and a *simulated* flag so
the dashboard can never present simulated data as real hardware data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SensorStatus(str, Enum):
    OK = "OK"
    STALE = "STALE"
    ERROR = "ERROR"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"


class SensorReading(BaseModel):
    """A single typed sensor reading.

    ``value`` may be ``None`` when the sensor is not configured or errored;
    missing values are never coerced to zero.
    """

    model_config = ConfigDict(extra="forbid")

    sensor: str
    value: float | int | bool | str | None = None
    unit: str = ""
    status: SensorStatus = SensorStatus.OK
    timestamp: datetime = Field(default_factory=_utcnow)
    simulated: bool = False
    detail: str = ""


class TelemetrySnapshot(BaseModel):
    """A coherent snapshot of all sensors at one point in time."""

    model_config = ConfigDict(extra="forbid")

    device_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    simulated: bool = False
    readings: dict[str, SensorReading] = Field(default_factory=dict)

    def reading(self, sensor: str) -> SensorReading | None:
        return self.readings.get(sensor)
