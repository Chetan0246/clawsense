"""Background control loop.

Drives the supervisor's control cycle at a fixed cadence.  In simulation mode
this advances the simulated device; in hardware mode it polls the ESP32 over
the configured transport.  The loop is defensive: an unexpected error is
logged and the loop continues rather than dying silently.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.services.supervisor import Supervisor

logger = logging.getLogger("clawsense.loop")


class ControlLoop:
    def __init__(self, supervisor: Supervisor, settings: Settings) -> None:
        self.supervisor = supervisor
        self.settings = settings
        self._task: asyncio.Task | None = None
        self._running = False
        self.cycles = 0
        self.errors = 0

    async def _run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self.supervisor.control_cycle()
                self.cycles += 1
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive
                self.errors += 1
                logger.exception("Control cycle failed: %s", exc)
            try:
                await asyncio.sleep(self.settings.simulator_interval_seconds)
            except asyncio.CancelledError:
                break
        self._running = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
