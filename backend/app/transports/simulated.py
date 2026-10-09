"""Simulated device transport (no hardware required)."""

from __future__ import annotations

import asyncio
from enum import Enum

from app.schemas.telemetry import TelemetrySnapshot
from app.simulation.device import SimulatedEsp32
from app.transports.base import AckResult, DeviceTransport


class FailureMode(str, Enum):
    """Injectable failure modes used by the demo and tests."""

    NONE = "none"
    TIMEOUT = "timeout"
    REJECT = "reject"
    UNCERTAIN = "uncertain"


class SimulatedDeviceTransport(DeviceTransport):
    """Transport backed by :class:`SimulatedEsp32`."""

    def __init__(self, device: SimulatedEsp32, latency_ms: float = 0.0) -> None:
        self.device = device
        self.latency_ms = latency_ms
        self.failure_mode = FailureMode.NONE
        self.dispatched: list[tuple[str, dict]] = []

    def set_failure_mode(self, mode: FailureMode) -> None:
        self.failure_mode = mode

    async def send_command(
        self, device_id: str, action: str, parameters: dict
    ) -> AckResult:
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

        if self.failure_mode == FailureMode.TIMEOUT:
            return AckResult(
                acknowledged=False,
                detail="Simulated device did not acknowledge in time.",
                error="DEVICE_TIMEOUT",
                simulated=True,
            )
        if self.failure_mode == FailureMode.REJECT:
            return AckResult(
                acknowledged=False,
                detail="Simulated device rejected the command.",
                error="DEVICE_REJECTED",
                simulated=True,
            )
        if self.failure_mode == FailureMode.UNCERTAIN:
            return AckResult(
                acknowledged=False,
                state_confirmed=False,
                detail="Communication uncertainty: acknowledgement not received.",
                error="COMMUNICATION_UNCERTAINTY",
                simulated=True,
            )

        state = self.device.apply_command(action, parameters)
        self.dispatched.append((action, dict(parameters)))
        return AckResult(
            acknowledged=True,
            state_confirmed=True,
            detail="Simulated device applied command.",
            latency_ms=self.latency_ms,
            reported_state=state,
            simulated=True,
        )

    async def get_telemetry(self, device_id: str) -> TelemetrySnapshot | None:
        # Advancing the device each acquisition makes the simulated sensors
        # evolve deterministically over time.
        return self.device.step()

    async def health(self, device_id: str) -> bool:
        return self.failure_mode != FailureMode.TIMEOUT
