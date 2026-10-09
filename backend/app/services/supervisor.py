"""ClawSense supervisor / orchestrator.

The single place where telemetry, context, the agent, the deterministic safety
supervisor, the state machine, the fallback controller, and the command
dispatcher are composed into one control loop.

Control flow per cycle::

    telemetry -> context/event engine -> state evaluation
              -> controller (agent when ONLINE/DEGRADED, fallback when local)
              -> proposal -> SAFETY VALIDATION -> dispatch -> ack

The LLM is never on the execution path: its output is only ever a *proposal*.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.config import Settings
from app.repositories.command_repository import CommandRepository
from app.repositories.decision_repository import DecisionRepository
from app.repositories.event_repository import EventRepository
from app.repositories.proposal_repository import ProposalRepository
from app.repositories.telemetry_repository import TelemetryRepository
from app.repositories.transition_repository import TransitionRepository
from app.schemas.actions import ActionName, ActionProposal
from app.schemas.commands import CommandRecord
from app.schemas.events import EventCategory, EventRecord, EventType, Severity
from app.schemas.safety import SafetyResult
from app.schemas.system import StateTransition, SystemState
from app.schemas.telemetry import TelemetrySnapshot
from app.services.agent_adapter import (
    AgentAdapter,
    AgentTimeout,
    AgentUnavailable,
    SimulatedAgent,
)
from app.services.audit import AuditLog
from app.services.command_dispatcher import CommandDispatcher
from app.services.context_memory import ContextMemory
from app.services.event_bus import EventBus
from app.services.event_engine import EventEngine
from app.services.fallback_controller import FallbackController
from app.services.safety_supervisor import SafetySupervisor
from app.services.state_machine import (
    RC_RECOVERY_COMPLETED,
    RC_RECOVERY_HEALTHCHECK_FAILED,
    RC_CONNECTIVITY_RESTORED,
    RC_CRITICAL_FAULT,
    RC_FAULT_CLEARED,
    SystemStateMachine,
)
from app.simulation.device import Scenario, SimulatedEsp32
from app.transports.base import DeviceTransport
from app.transports.simulated import FailureMode, SimulatedDeviceTransport

# Reason codes for supervisor-originated transitions.
RC_MANUAL_LOCKDOWN = "MANUAL_LOCKDOWN"
RC_MANUAL_RESET = "MANUAL_RESET"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Supervisor:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: DeviceTransport,
        state_machine: SystemStateMachine,
        agent: AgentAdapter,
        device: SimulatedEsp32 | None,
        bus: EventBus,
        telemetry_repository: TelemetryRepository,
        proposal_repository: ProposalRepository,
        decision_repository: DecisionRepository,
        command_repository: CommandRepository,
        event_repository: EventRepository,
        transition_repository: TransitionRepository,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.state_machine = state_machine
        self.agent = agent
        self.device = device
        self.bus = bus

        self.telemetry_repo = telemetry_repository
        self.proposal_repo = proposal_repository
        self.decision_repo = decision_repository
        self.command_repo = command_repository
        self.event_repo = event_repository
        self.transition_repo = transition_repository

        self.context = ContextMemory()
        self.audit = AuditLog(
            event_repository, bus, self.context, simulated=settings.is_simulation
        )
        self.event_engine = EventEngine(settings, bus)
        self.safety = SafetySupervisor(settings)
        self.fallback = FallbackController(settings)
        self.dispatcher = CommandDispatcher(
            settings,
            transport,
            command_repository,
            self.audit,
            state_machine,
            self.context,
            bus,
        )

        self.latest_telemetry: TelemetrySnapshot | None = None
        self.latest_decision: SafetyResult | None = None
        self.latest_command: CommandRecord | None = None

        self._last_auto_key: tuple | None = None
        self._last_auto_at: datetime | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Telemetry ingestion
    # ------------------------------------------------------------------
    async def ingest_telemetry(self, snapshot: TelemetrySnapshot) -> list[EventRecord]:
        self.latest_telemetry = snapshot
        self.context.update_telemetry(snapshot)

        for reading in snapshot.readings.values():
            self.telemetry_repo.insert_reading(snapshot.device_id, reading)

        events = self.event_engine.process(snapshot)
        for event in events:
            self.audit.record(event)

        self.bus.publish(
            {"type": "telemetry", "data": snapshot.model_dump(mode="json")}
        )
        return events

    async def _acquire_telemetry(self) -> TelemetrySnapshot | None:
        snapshot = await self.transport.get_telemetry(self.settings.device_id)
        return snapshot

    # ------------------------------------------------------------------
    # Safety-validated proposal handling
    # ------------------------------------------------------------------
    async def handle_proposal(
        self, proposal: ActionProposal, *, is_fallback: bool = False
    ) -> tuple[SafetyResult, CommandRecord | None]:
        """Validate and (if approved) dispatch a single proposal."""
        self.proposal_repo.insert(proposal, simulated=self.settings.is_simulation)
        self.audit.emit(
            EventType.FALLBACK_ACTION if is_fallback else EventType.AGENT_PROPOSAL,
            EventCategory.OFFLINE_FALLBACK if is_fallback else EventCategory.AGENT_PROPOSAL,
            source="fallback_controller" if is_fallback else "agent",
            device_id=self.settings.device_id,
            proposal_id=proposal.proposal_id,
            details={
                "action": proposal.action.value,
                "parameters": proposal.parameters,
                "reason": proposal.reason,
            },
        )

        decision = self.safety.validate(
            proposal, self.state_machine.current_state, self.context
        )
        if decision.approved:
            decision.dispatch_attempted = True
        self.decision_repo.insert(decision, simulated=self.settings.is_simulation)
        self.latest_decision = decision

        if decision.approved:
            self.audit.emit(
                EventType.ACTION_APPROVED,
                EventCategory.SAFETY_APPROVAL,
                source="safety_supervisor",
                device_id=self.settings.device_id,
                proposal_id=proposal.proposal_id,
                details={
                    "decision_id": decision.decision_id,
                    "reason_code": decision.reason_code,
                    "checks": decision.checks,
                },
            )
        else:
            self.audit.emit(
                EventType.ACTION_REJECTED,
                EventCategory.SAFETY_REJECTION,
                source="safety_supervisor",
                severity=Severity.WARNING,
                device_id=self.settings.device_id,
                proposal_id=proposal.proposal_id,
                details={
                    "decision_id": decision.decision_id,
                    "reason_code": decision.reason_code,
                    "reason": decision.reason,
                    "checks": decision.checks,
                },
            )

        self.bus.publish(
            {"type": "decision", "data": decision.model_dump(mode="json")}
        )

        command: CommandRecord | None = None
        if decision.approved:
            command = await self.dispatcher.dispatch(proposal, decision)
            self.latest_command = command
        return decision, command

    async def submit_proposal(
        self, proposal: ActionProposal, *, is_fallback: bool = False
    ) -> tuple[SafetyResult, CommandRecord | None]:
        """Public entry point (used by the API and demo) — always processed."""
        async with self._lock:
            return await self.handle_proposal(proposal, is_fallback=is_fallback)

    # ------------------------------------------------------------------
    # Controller selection
    # ------------------------------------------------------------------
    async def control_cycle(self) -> None:
        async with self._lock:
            snapshot = await self._acquire_telemetry()
            if snapshot is not None:
                await self.ingest_telemetry(snapshot)

            await self.evaluate_state()

            state = self.state_machine.current_state
            if state == SystemState.SAFE_LOCKDOWN:
                return
            if state in (SystemState.ONLINE_AGENT, SystemState.DEGRADED):
                await self._agent_cycle()
            else:
                await self._fallback_cycle()

    async def _agent_cycle(self) -> None:
        context_summary = self.context.summary()
        try:
            proposal = await asyncio.wait_for(
                self.agent.propose(context_summary),
                timeout=self.settings.agent_timeout_seconds,
            )
        except AgentTimeout as exc:
            self.state_machine.on_agent_failure()
            self.audit.emit(
                EventType.AGENT_TIMEOUT,
                EventCategory.AGENT_TIMEOUT,
                source="supervisor",
                severity=Severity.WARNING,
                device_id=self.settings.device_id,
                details={"error": str(exc)},
            )
            return
        except AgentUnavailable as exc:
            self.state_machine.on_agent_failure()
            self.audit.emit(
                EventType.AGENT_TIMEOUT,
                EventCategory.AGENT_TIMEOUT,
                source="supervisor",
                severity=Severity.WARNING,
                device_id=self.settings.device_id,
                details={"error": str(exc), "reason": "agent_unavailable"},
            )
            return
        except Exception as exc:  # pragma: no cover - defensive
            self.state_machine.on_agent_failure()
            self.audit.emit(
                EventType.AGENT_TIMEOUT,
                EventCategory.AGENT_TIMEOUT,
                source="supervisor",
                severity=Severity.ERROR,
                device_id=self.settings.device_id,
                details={"error": f"unexpected agent error: {exc}"},
            )
            return

        # A successful round-trip keeps the system online even if the agent
        # decided to do nothing.
        self.state_machine.on_agent_success()

        if proposal is None:
            return
        if proposal.action == ActionName.NO_OP:
            return
        if self._is_auto_duplicate(proposal):
            return
        await self.handle_proposal(proposal, is_fallback=False)

    async def _fallback_cycle(self) -> None:
        proposals = self.fallback.evaluate(self.context)
        for proposal in proposals:
            if proposal.action == ActionName.NO_OP:
                continue
            if self._is_auto_duplicate(proposal):
                continue
            await self.handle_proposal(proposal, is_fallback=True)

    def _is_auto_duplicate(self, proposal: ActionProposal) -> bool:
        """Suppress repeated identical automatic proposals within cooldown."""
        key = (proposal.action.value, tuple(sorted(proposal.parameters.items())))
        now = _utcnow()
        if (
            self._last_auto_key == key
            and self._last_auto_at is not None
            and (now - self._last_auto_at).total_seconds()
            < self.settings.action_cooldown_seconds
        ):
            return True
        self._last_auto_key = key
        self._last_auto_at = now
        return False

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------
    async def evaluate_state(self) -> StateTransition | None:
        transition = self.state_machine.evaluate()
        if transition is None:
            return None
        self._persist_transition(transition)
        return transition

    def _persist_transition(self, transition: StateTransition) -> None:
        self.transition_repo.insert(transition)
        self.audit.emit(
            EventType.STATE_TRANSITION,
            EventCategory.STATE_TRANSITION,
            source="state_machine",
            severity=Severity.WARNING
            if transition.new_state in (SystemState.DEGRADED, SystemState.SAFE_LOCKDOWN)
            else Severity.INFO,
            device_id=self.settings.device_id,
            details={
                "previous_state": transition.previous_state.value
                if transition.previous_state
                else None,
                "new_state": transition.new_state.value,
                "reason_code": transition.reason_code,
                "reason": transition.reason,
            },
            timestamp=transition.timestamp,
        )
        if transition.new_state == SystemState.OFFLINE_LOCAL:
            self.audit.emit(
                EventType.FALLBACK_ACTIVATED,
                EventCategory.OFFLINE_FALLBACK,
                source="state_machine",
                severity=Severity.WARNING,
                details={"reason_code": transition.reason_code},
            )
        elif transition.new_state == SystemState.RECOVERY:
            self.audit.emit(
                EventType.RECOVERY_STARTED,
                EventCategory.RECOVERY,
                source="state_machine",
                details={"reason_code": transition.reason_code},
            )
        elif (
            transition.new_state == SystemState.ONLINE_AGENT
            and transition.reason_code == RC_RECOVERY_COMPLETED
        ):
            self.audit.emit(
                EventType.RECOVERY_COMPLETED,
                EventCategory.RECOVERY,
                source="state_machine",
                details={"reason_code": transition.reason_code},
            )
        self._publish_state()

    def _publish_state(self) -> None:
        self.bus.publish(
            {"type": "system", "data": self.state_machine.status().model_dump(mode="json")}
        )

    async def force_state(
        self, new_state: SystemState, reason_code: str, reason: str
    ) -> StateTransition:
        async with self._lock:
            transition = self.state_machine.request_transition(
                new_state, reason_code, reason, simulated=self.settings.is_simulation
            )
            self._persist_transition(transition)
            return transition

    async def trigger_lockdown(self, reason: str) -> StateTransition:
        return await self.force_state(SystemState.SAFE_LOCKDOWN, RC_CRITICAL_FAULT, reason)

    async def reset_lockdown(self) -> StateTransition:
        """Exit SAFE_LOCKDOWN into RECOVERY (the only permitted exit)."""
        return await self.force_state(
            SystemState.RECOVERY,
            RC_FAULT_CLEARED,
            "Operator cleared the critical fault; entering recovery validation.",
        )

    # ------------------------------------------------------------------
    # Simulation / demo controls
    # ------------------------------------------------------------------
    def set_scenario(self, scenario: Scenario) -> None:
        if self.device is not None:
            self.device.set_scenario(scenario)
        self.audit.emit(
            EventType.STATE_TRANSITION,
            EventCategory.CONFIG_CHANGE,
            source="operator",
            details={"scenario": scenario.value},
        )

    def set_agent_available(self, available: bool) -> None:
        """Force the agent health signal (used by the demo/tests).

        For the simulated agent this also flips its reachability so the
        state machine genuinely degrades instead of being immediately
        re-marked healthy on the next successful proposal.
        """
        if isinstance(self.agent, SimulatedAgent):
            self.agent.forced_unavailable = not available
        if available:
            self.state_machine.on_agent_success()
        else:
            self.state_machine.on_agent_failure()

    def set_failure_mode(self, mode: FailureMode) -> None:
        if isinstance(self.transport, SimulatedDeviceTransport):
            self.transport.set_failure_mode(mode)

    def status_payload(self) -> dict:
        return self.state_machine.status().model_dump(mode="json")
