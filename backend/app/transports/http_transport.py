"""HTTP device transport for a real ESP32-S3 node (PLAN.md section 14).

The firmware exposes:
    GET  /health
    GET  /telemetry
    POST /command

The command endpoint expects a JSON body::

    {"command_id": "...", "action": "servo_move", "parameters": {...}}

and responds with an acknowledgement::

    {"acknowledged": true, "state_confirmed": true, "reported_state": {...}}

This transport is only used when ``CLAWSENSE_APP_MODE=hardware``.  It performs
retries with a bounded attempt count and never blocks indefinitely.
"""

from __future__ import annotations

import time

import httpx

from app.config import Settings
from app.schemas.telemetry import SensorReading, SensorStatus, TelemetrySnapshot
from app.transports.base import AckResult, DeviceTransport


class HttpDeviceTransport(DeviceTransport):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.device_base_url.rstrip("/")

    async def send_command(
        self, device_id: str, action: str, parameters: dict
    ) -> AckResult:
        payload = {"action": action, "parameters": parameters}
        attempts = max(1, self.settings.device_retry_attempts + 1)
        timeout = self.settings.device_command_timeout_seconds
        last_error: str | None = None
        started = time.monotonic()
        async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
            for _ in range(attempts):
                try:
                    resp = await client.post("/command", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return AckResult(
                        acknowledged=bool(data.get("acknowledged", False)),
                        state_confirmed=bool(data.get("state_confirmed", False)),
                        detail=str(data.get("detail", "")),
                        latency_ms=(time.monotonic() - started) * 1000.0,
                        reported_state=data.get("reported_state", {}) or {},
                        simulated=False,
                    )
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    continue
                except httpx.HTTPStatusError as exc:
                    last_error = f"HTTP {exc.response.status_code}"
                    break
        return AckResult(
            acknowledged=False,
            state_confirmed=False,
            detail="Device did not acknowledge.",
            error=last_error or "DEVICE_TIMEOUT",
            latency_ms=(time.monotonic() - started) * 1000.0,
            simulated=False,
        )

    async def get_telemetry(self, device_id: str) -> TelemetrySnapshot | None:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.settings.device_command_timeout_seconds,
            ) as client:
                resp = await client.get("/telemetry")
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

        readings: dict[str, SensorReading] = {}
        for name, payload in (data.get("readings") or {}).items():
            if isinstance(payload, dict):
                readings[name] = SensorReading(
                    sensor=name,
                    value=payload.get("value"),
                    unit=payload.get("unit", ""),
                    status=SensorStatus(payload.get("status", "OK")),
                    simulated=False,
                )
        return TelemetrySnapshot(
            device_id=device_id,
            simulated=False,
            readings=readings,
        )

    async def health(self, device_id: str) -> bool:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.settings.device_command_timeout_seconds,
            ) as client:
                resp = await client.get("/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
