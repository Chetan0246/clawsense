"""Agent / LLM adapter (PLAN.md section 12).

The agent proposes structured actions.  It never touches GPIO, never validates
its own output, and never executes anything.  Two implementations are provided:

* :class:`SimulatedAgent` — deterministic, offline, used for demos/tests.
* :class:`EspClawAgent` — an adapter for a real ESPClaw / LLM endpoint.

If the real integration is unavailable or misconfigured, the adapter fails
closed and the state machine degrades to the local fallback controller.  An
agent response that cannot be parsed into the action contract is discarded.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from enum import Enum

import httpx

from app.config import Settings
from app.schemas.actions import ActionName, ActionProposal
from app.simulation.device import SimulatedEsp32


class AgentError(Exception):
    """Base class for agent failures."""


class AgentUnavailable(AgentError):
    """The agent service is not reachable or not configured."""


class AgentTimeout(AgentError):
    """The agent did not respond within the configured timeout."""


class AgentAdapter(ABC):
    name: str = "agent"

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether the adapter is currently usable."""

    @abstractmethod
    async def propose(self, context: dict) -> ActionProposal | None:
        """Return a proposed action, or ``None`` for an intentional no-op."""


class SimulatedAgent(AgentAdapter):
    """Deterministic offline agent used for the simulation demo.

    The decision rules are intentionally simple and explicit so that the
    *supervisory* architecture (not the AI) is the focus of the project.
    """

    name = "simulated"

    class Mode(str, Enum):
        AUTO = "auto"
        UNSAFE_ANGLE = "unsafe_angle"
        LED_ALERT = "led_alert"
        NOOP = "noop"

    def __init__(self, settings: Settings, device: SimulatedEsp32 | None = None) -> None:
        self.settings = settings
        self.device = device
        self.mode = self.Mode.AUTO
        #: When True the agent simulates being unreachable so the state machine
        #: can exercise the DEGRADED/OFFLINE_LOCAL paths deterministically.
        self.forced_unavailable = False

    @property
    def available(self) -> bool:
        return not self.forced_unavailable

    async def propose(self, context: dict) -> ActionProposal | None:
        if self.forced_unavailable:
            raise AgentUnavailable("Simulated agent is forced offline.")

        readings = context.get("latest_readings", {})
        temp = self._value(readings, "temperature_c")
        motion = self._value(readings, "motion")

        if self.mode == self.Mode.UNSAFE_ANGLE:
            # Deliberately unsafe proposal used to demonstrate deterministic
            # rejection.  It is NOT executed.
            return ActionProposal(
                action=ActionName.SERVO_MOVE,
                parameters={"angle_degrees": 250},
                reason="Simulated agent proposed an out-of-range angle (demo).",
                source="agent",
            )
        if self.mode == self.Mode.NOOP:
            return ActionProposal(
                action=ActionName.NO_OP,
                parameters={},
                reason="No action required.",
                source="agent",
            )
        if self.mode == self.Mode.LED_ALERT:
            return ActionProposal(
                action=ActionName.SET_STATUS_LED,
                parameters={"color": "red"},
                reason="Operator-requested alert indicator.",
                source="agent",
            )

        # AUTO mode.
        if temp is not None and temp > self.settings.temp_high_c:
            return ActionProposal(
                action=ActionName.SET_STATUS_LED,
                parameters={"color": "red"},
                reason=f"Temperature {temp}C exceeds threshold; raise alert LED.",
                source="agent",
            )
        if motion:
            return ActionProposal(
                action=ActionName.SERVO_MOVE,
                parameters={"angle_degrees": 45},
                reason="Motion detected; move servo to observation position.",
                source="agent",
            )
        return ActionProposal(
            action=ActionName.NO_OP,
            parameters={},
            reason="Conditions nominal.",
            source="agent",
        )

    @staticmethod
    def _value(readings: dict, key: str):
        entry = readings.get(key)
        if isinstance(entry, dict):
            return entry.get("value")
        return None


class EspClawAgent(AgentAdapter):
    """Adapter for a real ESPClaw / LLM endpoint.

    Integration contract (see docs/architecture.md):
        POST {endpoint}/propose
        body: {"context": <bounded context summary>}
        response: {"action": "...", "parameters": {...}, "reason": "..."}

    Any response that does not validate against the action contract is
    discarded (returns ``None``), and transport failures raise
    :class:`AgentUnavailable` so the state machine can degrade gracefully.
    """

    name = "espclaw"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.endpoint = settings.espclaw_endpoint.rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self.endpoint)

    async def propose(self, context: dict) -> ActionProposal | None:
        if not self.available:
            raise AgentUnavailable("ESPClaw endpoint is not configured.")

        timeout = self.settings.agent_timeout_seconds
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.endpoint}/propose",
                    json={"context": context},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise AgentTimeout(f"Agent timed out after {timeout}s.") from exc
        except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
            raise AgentUnavailable(f"Agent request failed: {exc}") from exc

        if not isinstance(data, dict) or "action" not in data:
            # Unparseable response -> discard, do not guess.
            return None

        try:
            return ActionProposal(
                action=data["action"],
                parameters=data.get("parameters", {}) or {},
                reason=str(data.get("reason", ""))[:1000],
                source="agent",
            )
        except Exception:
            # Never allow a malformed agent response to become an action.
            return None

    def _headers(self) -> dict:
        # Secrets are attached server-side only and never logged or returned.
        if self.settings.llm_api_key:
            return {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        return {}


def create_agent(settings: Settings, device: SimulatedEsp32 | None = None) -> AgentAdapter:
    """Build the configured agent adapter."""
    if settings.agent_provider == "espclaw":
        return EspClawAgent(settings)
    return SimulatedAgent(settings, device=device)
