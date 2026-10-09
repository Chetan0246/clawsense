"""System state machine (PLAN.md section 11).

Explicit states, explicit transitions, and explicit transition reasons.  Every
transition is validated against the allowed transition table; illegal
transitions are refused rather than silently applied.

    ONLINE_AGENT -> DEGRADED            (agent slow / first failure)
    DEGRADED     -> OFFLINE_LOCAL       (agent unreachable beyond timeout)
    DEGRADED     -> ONLINE_AGENT        (recovered quickly)
    OFFLINE_LOCAL-> RECOVERY            (connectivity restored)
    RECOVERY     -> ONLINE_AGENT        (health checks pass)
    RECOVERY     -> OFFLINE_LOCAL       (health checks fail)
    ANY          -> SAFE_LOCKDOWN       (critical fault)
    SAFE_LOCKDOWN-> RECOVERY            (fault cleared + reset policy)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import Settings
from app.schemas.system import StateTransition, SystemState, SystemStatus

# Reason codes
RC_STARTUP = "STARTUP"
RC_AGENT_UNREACHABLE = "AGENT_UNREACHABLE"
RC_AGENT_UNREACHABLE_PERSISTENT = "AGENT_UNREACHABLE_PERSISTENT"
RC_AGENT_RECOVERED = "AGENT_RECOVERED"
RC_CONNECTIVITY_RESTORED = "CONNECTIVITY_RESTORED"
RC_RECOVERY_HEALTHCHECK_FAILED = "RECOVERY_HEALTHCHECK_FAILED"
RC_RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
RC_CRITICAL_FAULT = "CRITICAL_FAULT"
RC_FAULT_CLEARED = "FAULT_CLEARED"
RC_ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"

ALLOWED_TRANSITIONS: dict[SystemState, set[SystemState]] = {
    SystemState.ONLINE_AGENT: {SystemState.DEGRADED, SystemState.SAFE_LOCKDOWN},
    SystemState.DEGRADED: {
        SystemState.ONLINE_AGENT,
        SystemState.OFFLINE_LOCAL,
        SystemState.SAFE_LOCKDOWN,
    },
    SystemState.OFFLINE_LOCAL: {
        SystemState.RECOVERY,
        SystemState.SAFE_LOCKDOWN,
    },
    SystemState.RECOVERY: {
        SystemState.ONLINE_AGENT,
        SystemState.OFFLINE_LOCAL,
        SystemState.SAFE_LOCKDOWN,
    },
    SystemState.SAFE_LOCKDOWN: {SystemState.RECOVERY},
}

#: Authority that may drive actuators in each state.
_AUTHORITY = {
    SystemState.ONLINE_AGENT: "agent",
    SystemState.DEGRADED: "agent",
    SystemState.OFFLINE_LOCAL: "local",
    SystemState.RECOVERY: "local",
    SystemState.SAFE_LOCKDOWN: "none",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InvalidTransition(Exception):
    """Raised when a transition is not permitted by the state machine."""


@dataclass
class SystemStateMachine:
    settings: Settings
    current_state: SystemState = SystemState.ONLINE_AGENT
    previous_state: SystemState | None = None
    transition_reason_code: str | None = None
    transition_reason: str = ""
    last_transition_at: datetime | None = None

    agent_available: bool = True
    network_available: bool = True
    device_connected: bool = False
    last_successful_agent_request: datetime | None = None
    last_successful_device_communication: datetime | None = None
    recovery_status: str = "idle"
    started_at: datetime = field(default_factory=_utcnow)

    # -- event hooks -------------------------------------------------------
    def __post_init__(self) -> None:
        self.last_successful_agent_request = self.last_successful_agent_request or _utcnow()

    # -- transition --------------------------------------------------------
    def can_transition(self, new_state: SystemState) -> bool:
        if new_state == self.current_state:
            return False
        return new_state in ALLOWED_TRANSITIONS.get(self.current_state, set())

    def request_transition(
        self,
        new_state: SystemState,
        reason_code: str,
        reason: str = "",
        *,
        diagnostics: dict | None = None,
        simulated: bool = False,
        now: datetime | None = None,
        force: bool = False,
    ) -> StateTransition:
        """Apply a validated transition or raise :class:`InvalidTransition`."""
        now = now or _utcnow()
        if new_state == self.current_state:
            raise InvalidTransition(
                f"Already in state {new_state.value}"
            )
        if not force and not self.can_transition(new_state):
            raise InvalidTransition(
                f"Illegal transition {self.current_state.value} -> {new_state.value}"
            )

        transition = StateTransition(
            previous_state=self.current_state,
            new_state=new_state,
            reason_code=reason_code,
            reason=reason,
            timestamp=now,
            simulated=simulated,
            diagnostics=diagnostics or {},
        )
        self.previous_state = self.current_state
        self.current_state = new_state
        self.transition_reason_code = reason_code
        self.transition_reason = reason
        self.last_transition_at = now
        if new_state == SystemState.RECOVERY:
            self.recovery_status = "in_progress"
        elif new_state == SystemState.ONLINE_AGENT:
            self.recovery_status = "complete"
        elif new_state == SystemState.OFFLINE_LOCAL:
            self.recovery_status = "idle"
        return transition

    # -- health signals ----------------------------------------------------
    def on_agent_success(self, now: datetime | None = None) -> None:
        self.last_successful_agent_request = now or _utcnow()
        self.agent_available = True

    def on_agent_failure(self) -> None:
        self.agent_available = False

    def on_device_success(self, now: datetime | None = None) -> None:
        self.last_successful_device_communication = now or _utcnow()
        self.device_connected = True

    def on_device_failure(self) -> None:
        self.device_connected = False

    def set_network(self, available: bool) -> None:
        self.network_available = available

    def trigger_lockdown(
        self,
        reason_code: str = RC_CRITICAL_FAULT,
        reason: str = "Critical fault detected.",
        *,
        diagnostics: dict | None = None,
        now: datetime | None = None,
    ) -> StateTransition:
        return self.request_transition(
            SystemState.SAFE_LOCKDOWN,
            reason_code,
            reason,
            diagnostics=diagnostics,
            now=now,
        )

    # -- automatic evaluation ---------------------------------------------
    def evaluate(self, now: datetime | None = None) -> StateTransition | None:
        """Evaluate health and return a transition to apply, if any.

        Returns ``None`` when no transition is warranted.  The caller is
        responsible for persisting the returned transition and emitting events.
        """
        now = now or _utcnow()
        if self.current_state == SystemState.SAFE_LOCKDOWN:
            return None

        healthy = self.agent_available and self.network_available
        last = self.last_successful_agent_request
        elapsed = (now - last).total_seconds() if last else float("inf")

        # Connectivity restored.
        if healthy:
            if self.current_state in (SystemState.DEGRADED, SystemState.RECOVERY):
                return self.request_transition(
                    SystemState.ONLINE_AGENT,
                    RC_AGENT_RECOVERED
                    if self.current_state == SystemState.DEGRADED
                    else RC_RECOVERY_COMPLETED,
                    "Agent and network are healthy again.",
                    now=now,
                )
            if self.current_state == SystemState.OFFLINE_LOCAL:
                return self.request_transition(
                    SystemState.RECOVERY,
                    RC_CONNECTIVITY_RESTORED,
                    "Connectivity restored; validating system health.",
                    now=now,
                )
            return None

        # Agent / network unavailable.
        if self.current_state == SystemState.ONLINE_AGENT:
            # The first failure always degrades; OFFLINE_LOCAL is only reached
            # from DEGRADED once the offline timeout is exceeded.
            if elapsed > self.settings.degraded_timeout_seconds:
                return self.request_transition(
                    SystemState.DEGRADED,
                    RC_AGENT_UNREACHABLE,
                    "Agent unreachable beyond degraded timeout.",
                    diagnostics={"elapsed_seconds": elapsed},
                    now=now,
                )
            return None

        if self.current_state == SystemState.DEGRADED:
            if elapsed > self.settings.offline_timeout_seconds:
                return self.request_transition(
                    SystemState.OFFLINE_LOCAL,
                    RC_AGENT_UNREACHABLE_PERSISTENT,
                    "Agent still unreachable beyond offline timeout.",
                    diagnostics={"elapsed_seconds": elapsed},
                    now=now,
                )
            return None

        if self.current_state == SystemState.RECOVERY:
            # Health check failed while recovering.
            return self.request_transition(
                SystemState.OFFLINE_LOCAL,
                RC_RECOVERY_HEALTHCHECK_FAILED,
                "Health checks failed during recovery; returning to local control.",
                now=now,
            )

        return None

    # -- status ------------------------------------------------------------
    @property
    def controller_authority(self) -> str:
        return _AUTHORITY.get(self.current_state, "none")

    def status(self, now: datetime | None = None) -> SystemStatus:
        now = now or _utcnow()
        return SystemStatus(
            current_state=self.current_state,
            previous_state=self.previous_state,
            transition_reason_code=self.transition_reason_code,
            transition_reason=self.transition_reason,
            last_transition_at=self.last_transition_at,
            controller_authority=self.controller_authority,
            agent_available=self.agent_available,
            agent_provider=self.settings.agent_provider,
            network_available=self.network_available,
            device_connected=self.device_connected,
            last_successful_agent_request=self.last_successful_agent_request,
            last_successful_device_communication=(
                self.last_successful_device_communication
            ),
            recovery_status=self.recovery_status,
            simulated=self.settings.is_simulation,
            uptime_seconds=(now - self.started_at).total_seconds(),
        )
