"""Command dispatcher and lifecycle tracking (PLAN.md section 15).

An approved backend action is NOT proof of a physical action.  The dispatcher
tracks the full lifecycle independently:

    PROPOSED -> VALIDATED -> APPROVED -> DISPATCHED -> ACKNOWLEDGED -> STATE_CONFIRMED

Communication failures result in ``TIMEOUT``/``FAILED``/``UNCERTAIN`` and a
degraded system state — never in a false claim of success.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.repositories.command_repository import CommandRepository
from app.schemas.actions import ActionName, ActionProposal
from app.schemas.commands import CommandRecord, CommandStatus
from app.schemas.events import EventCategory, EventType, Severity
from app.schemas.safety import SafetyResult
from app.services.audit import AuditLog
from app.services.context_memory import ContextMemory
from app.services.event_bus import EventBus
from app.services.state_machine import SystemStateMachine
from app.transports.base import DeviceTransport


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CommandDispatcher:
    def __init__(
        self,
        settings: Settings,
        transport: DeviceTransport,
        command_repository: CommandRepository,
        audit: AuditLog,
        state_machine: SystemStateMachine,
        context: ContextMemory,
        bus: EventBus,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.commands = command_repository
        self.audit = audit
        self.state_machine = state_machine
        self.context = context
        self.bus = bus

    def _publish_command(self, command: CommandRecord) -> None:
        self.bus.publish(
            {"type": "command", "data": command.model_dump(mode="json")}
        )

    def _set_status(
        self,
        command: CommandRecord,
        status: CommandStatus,
        *,
        acknowledged_at=None,
        error: str | None = None,
    ) -> None:
        command.status = status
        if acknowledged_at is not None:
            command.acknowledged_at = acknowledged_at
        if error is not None:
            command.error = error
        self.commands.update_status(
            command.command_id, status, acknowledged_at=acknowledged_at, error=error
        )
        self._publish_command(command)

    async def dispatch(
        self,
        proposal: ActionProposal,
        decision: SafetyResult,
        *,
        target_device: str | None = None,
    ) -> CommandRecord:
        target_device = target_device or self.settings.device_id
        command = CommandRecord(
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            target_device=target_device,
            action=proposal.action.value,
            parameters=proposal.parameters,
            status=CommandStatus.VALIDATED,
            expires_at=_utcnow()
            + timedelta(seconds=self.settings.command_ttl_seconds),
            simulated=self.settings.is_simulation,
        )
        self.commands.insert(command)
        self._publish_command(command)

        # Stale-command guard: never execute a command past its expiry.
        if command.expires_at is not None and _utcnow() >= command.expires_at:
            self._set_status(command, CommandStatus.FAILED, error="COMMAND_EXPIRED")
            self.audit.emit(
                EventType.DEVICE_FAILURE,
                EventCategory.DEVICE_FAILURE,
                source="command_dispatcher",
                severity=Severity.WARNING,
                device_id=target_device,
                proposal_id=proposal.proposal_id,
                command_id=command.command_id,
                details={"error": "COMMAND_EXPIRED"},
            )
            return command

        # Safety approval already established by the supervisor.
        self._set_status(command, CommandStatus.APPROVED)

        # no_op is a valid, intentional non-action: nothing to send.
        if proposal.action == ActionName.NO_OP:
            self._set_status(command, CommandStatus.STATE_CONFIRMED)
            self.audit.emit(
                EventType.COMMAND_ACKNOWLEDGED,
                EventCategory.COMMAND_DISPATCH,
                source="command_dispatcher",
                device_id=target_device,
                proposal_id=proposal.proposal_id,
                command_id=command.command_id,
                details={"action": "no_op", "note": "no-op; nothing dispatched"},
            )
            return command

        # Record the action for cooldown/duplicate enforcement regardless of
        # the eventual acknowledgement (conservative, fail-closed).
        self.context.record_action(
            proposal.action.value,
            proposal.parameters,
            command_id=command.command_id,
            proposal_id=proposal.proposal_id,
        )

        command.dispatched_at = _utcnow()
        self._set_status(command, CommandStatus.DISPATCHED)
        self.audit.emit(
            EventType.COMMAND_DISPATCHED,
            EventCategory.COMMAND_DISPATCH,
            source="command_dispatcher",
            device_id=target_device,
            proposal_id=proposal.proposal_id,
            command_id=command.command_id,
            details={"action": proposal.action.value, "parameters": proposal.parameters},
        )

        timeout = self.settings.device_command_timeout_seconds
        try:
            ack = await asyncio.wait_for(
                self.transport.send_command(
                    target_device, proposal.action.value, proposal.parameters
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            self._set_status(command, CommandStatus.TIMEOUT, error="DEVICE_TIMEOUT")
            self.state_machine.on_device_failure()
            self.audit.emit(
                EventType.DEVICE_TIMEOUT,
                EventCategory.DEVICE_FAILURE,
                source="command_dispatcher",
                severity=Severity.ERROR,
                device_id=target_device,
                proposal_id=proposal.proposal_id,
                command_id=command.command_id,
                details={"timeout_seconds": timeout},
            )
            return command
        except Exception as exc:  # transport-level unexpected error
            self._set_status(command, CommandStatus.FAILED, error=str(exc))
            self.state_machine.on_device_failure()
            self.audit.emit(
                EventType.DEVICE_FAILURE,
                EventCategory.DEVICE_FAILURE,
                source="command_dispatcher",
                severity=Severity.ERROR,
                device_id=target_device,
                proposal_id=proposal.proposal_id,
                command_id=command.command_id,
                details={"error": str(exc)},
            )
            return command

        if not ack.acknowledged:
            if ack.error == "COMMUNICATION_UNCERTAINTY":
                status = CommandStatus.UNCERTAIN
            elif ack.error == "DEVICE_TIMEOUT":
                status = CommandStatus.TIMEOUT
            else:
                status = CommandStatus.FAILED
            self._set_status(command, status, error=ack.error)
            self.state_machine.on_device_failure()
            self.audit.emit(
                EventType.DEVICE_FAILURE,
                EventCategory.DEVICE_FAILURE,
                source="command_dispatcher",
                severity=Severity.ERROR,
                device_id=target_device,
                proposal_id=proposal.proposal_id,
                command_id=command.command_id,
                details={"error": ack.error, "detail": ack.detail},
            )
            return command

        command.acknowledged_at = _utcnow()
        self.state_machine.on_device_success()
        final_status = (
            CommandStatus.STATE_CONFIRMED
            if ack.state_confirmed
            else CommandStatus.ACKNOWLEDGED
        )
        self._set_status(
            command, final_status, acknowledged_at=command.acknowledged_at
        )
        self.audit.emit(
            EventType.COMMAND_ACKNOWLEDGED,
            EventCategory.DEVICE_ACK,
            source="command_dispatcher",
            device_id=target_device,
            proposal_id=proposal.proposal_id,
            command_id=command.command_id,
            details={
                "state_confirmed": ack.state_confirmed,
                "reported_state": ack.reported_state,
                "latency_ms": ack.latency_ms,
            },
        )
        return command
