"""Device transport abstraction (PLAN.md section 14).

The backend communicates with the ESP32-S3 through this narrow interface so
the simulated transport and the real HTTP transport are interchangeable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.schemas.telemetry import TelemetrySnapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AckResult:
    """Result of a command dispatch attempt."""

    acknowledged: bool
    state_confirmed: bool = False
    detail: str = ""
    latency_ms: float = 0.0
    error: str | None = None
    reported_state: dict = field(default_factory=dict)
    simulated: bool = False


class DeviceTransport(ABC):
    """Abstract device transport."""

    @abstractmethod
    async def send_command(
        self, device_id: str, action: str, parameters: dict
    ) -> AckResult:
        """Dispatch an approved command and await an acknowledgement."""

    @abstractmethod
    async def get_telemetry(self, device_id: str) -> TelemetrySnapshot | None:
        """Fetch the latest telemetry snapshot from the device."""

    @abstractmethod
    async def health(self, device_id: str) -> bool:
        """Return True when the device is reachable."""
