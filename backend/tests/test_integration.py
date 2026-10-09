"""End-to-end integration tests across the full supervisory pipeline."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.container import build_container
from app.schemas.actions import ActionName, ActionProposal
from app.schemas.commands import CommandStatus
from app.schemas.events import EventCategory, EventType
from app.schemas.system import SystemState
from app.services.agent_adapter import SimulatedAgent
from app.simulation.device import Scenario
from app.transports.simulated import FailureMode
from tests.conftest import make_settings

pytestmark = pytest.mark.asyncio


async def run_cycles(container, cycles: int = 1) -> None:
    for _ in range(cycles):
        await container.supervisor.control_cycle()


# ---------------------------------------------------------------------------
# Unsafe proposal is rejected and nothing is dispatched
# ---------------------------------------------------------------------------
async def test_unsafe_agent_proposal_is_rejected_and_device_unchanged():
    container = build_container(make_settings())
    container.agent.mode = SimulatedAgent.Mode.UNSAFE_ANGLE
    before = container.device.actuators.servo_angle

    await run_cycles(container, 1)

    decisions = container.decision_repo.list()
    assert decisions, "a decision must be recorded"
    assert decisions[0].approved is False
    assert decisions[0].reason_code == "ANGLE_OUT_OF_RANGE"
    assert decisions[0].dispatch_attempted is False

    # No command should exist and the servo must not have moved.
    assert container.command_repo.list() == []
    assert container.device.actuators.servo_angle == before
    assert container.transport.dispatched == []
    container.db.close()


# ---------------------------------------------------------------------------
# Agent unavailable -> degrade -> offline -> deterministic fallback
# ---------------------------------------------------------------------------
async def test_agent_failure_degrades_to_local_fallback():
    settings = make_settings(
        agent_provider="espclaw",
        espclaw_endpoint="",  # not configured -> AgentUnavailable
        degraded_timeout_seconds=0.0,
        offline_timeout_seconds=0.0,
    )
    container = build_container(settings)
    container.supervisor.set_scenario(Scenario.HEATWAVE)

    await run_cycles(container, 3)

    assert container.state_machine.current_state == SystemState.OFFLINE_LOCAL
    assert container.state_machine.controller_authority == "local"

    # Fallback must have produced a deterministic high-temperature response.
    commands = container.command_repo.list()
    actions = {c.action for c in commands}
    assert "set_status_led" in actions
    led_commands = [c for c in commands if c.action == "set_status_led"]
    assert led_commands[0].parameters["color"] == "red"
    assert led_commands[0].status in (
        CommandStatus.ACKNOWLEDGED,
        CommandStatus.STATE_CONFIRMED,
    )

    # Fallback activation must be audited.
    events, _ = container.event_repo.query(limit=500)
    categories = {e.category for e in events}
    assert EventCategory.OFFLINE_FALLBACK in categories
    container.db.close()


# ---------------------------------------------------------------------------
# Device communication failure handling
# ---------------------------------------------------------------------------
async def test_device_timeout_marks_command_timeout():
    settings = make_settings(device_command_timeout_seconds=0.05)
    container = build_container(settings)
    container.agent.mode = SimulatedAgent.Mode.NOOP
    container.transport.latency_ms = 200.0  # exceeds the dispatch timeout

    await run_cycles(container, 1)
    proposal = ActionProposal(
        action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 60}, source="operator"
    )
    decision, command = await container.supervisor.submit_proposal(proposal)

    assert decision.approved is True
    assert command is not None
    assert command.status == CommandStatus.TIMEOUT

    events, _ = container.event_repo.query(event_type=EventType.DEVICE_TIMEOUT.value)
    assert events, "a device-timeout event must be recorded"
    assert container.state_machine.device_connected is False
    container.db.close()


async def test_transport_reported_timeout_maps_to_timeout_status():
    container = build_container(make_settings())
    container.agent.mode = SimulatedAgent.Mode.NOOP
    container.supervisor.set_failure_mode(FailureMode.TIMEOUT)

    await run_cycles(container, 1)
    proposal = ActionProposal(
        action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 70}, source="operator"
    )
    decision, command = await container.supervisor.submit_proposal(proposal)

    assert decision.approved is True
    assert command is not None
    assert command.status == CommandStatus.TIMEOUT
    assert command.error == "DEVICE_TIMEOUT"
    container.db.close()


async def test_device_rejection_marks_command_failed():
    container = build_container(make_settings())
    container.agent.mode = SimulatedAgent.Mode.NOOP
    container.supervisor.set_failure_mode(FailureMode.REJECT)

    await run_cycles(container, 1)
    proposal = ActionProposal(
        action=ActionName.SET_STATUS_LED,
        parameters={"color": "green"},
        source="operator",
    )
    decision, command = await container.supervisor.submit_proposal(proposal)

    assert decision.approved is True
    assert command is not None
    assert command.status == CommandStatus.FAILED
    assert command.error == "DEVICE_REJECTED"
    container.db.close()


async def test_communication_uncertainty_is_not_reported_as_success():
    container = build_container(make_settings())
    container.agent.mode = SimulatedAgent.Mode.NOOP
    container.supervisor.set_failure_mode(FailureMode.UNCERTAIN)

    await run_cycles(container, 1)
    proposal = ActionProposal(
        action=ActionName.SET_STATUS_LED,
        parameters={"color": "yellow"},
        source="operator",
    )
    _, command = await container.supervisor.submit_proposal(proposal)

    assert command is not None
    assert command.status == CommandStatus.UNCERTAIN
    container.db.close()


# ---------------------------------------------------------------------------
# Audit completeness
# ---------------------------------------------------------------------------
async def test_audit_log_is_complete_for_rejected_proposal():
    container = build_container(make_settings())
    container.agent.mode = SimulatedAgent.Mode.UNSAFE_ANGLE
    await run_cycles(container, 1)

    proposal = container.proposal_repo.list()[0]
    events, _ = container.event_repo.query(limit=500)
    proposal_events = [e for e in events if e.proposal_id == proposal.proposal_id]
    types = {e.event_type for e in proposal_events}
    assert EventType.AGENT_PROPOSAL in types
    assert EventType.ACTION_REJECTED in types
    # The rejection is correlated to a persisted decision.
    decision = container.decision_repo.list()[0]
    assert decision.proposal_id == proposal.proposal_id
    container.db.close()


async def test_audit_log_is_complete_for_approved_proposal():
    container = build_container(make_settings())
    container.agent.mode = SimulatedAgent.Mode.NOOP
    await run_cycles(container, 1)

    proposal = ActionProposal(
        action=ActionName.SET_STATUS_LED,
        parameters={"color": "green"},
        source="operator",
    )
    _, command = await container.supervisor.submit_proposal(proposal)
    assert command is not None

    events, _ = container.event_repo.query(limit=500)
    types = {e.event_type for e in events if e.proposal_id == proposal.proposal_id}
    assert EventType.AGENT_PROPOSAL in types
    assert EventType.ACTION_APPROVED in types
    assert EventType.COMMAND_DISPATCHED in types
    assert EventType.COMMAND_ACKNOWLEDGED in types
    container.db.close()


# ---------------------------------------------------------------------------
# no_op is a valid, non-dispatched action
# ---------------------------------------------------------------------------
async def test_no_op_is_confirmed_without_dispatch():
    container = build_container(make_settings())
    await run_cycles(container, 1)
    before = len(container.transport.dispatched)

    proposal = ActionProposal(action=ActionName.NO_OP, parameters={}, source="operator")
    decision, command = await container.supervisor.submit_proposal(proposal)

    assert decision.approved is True
    assert command is not None
    assert command.status == CommandStatus.STATE_CONFIRMED
    assert len(container.transport.dispatched) == before
    container.db.close()


# ---------------------------------------------------------------------------
# Cooldown is enforced across the pipeline
# ---------------------------------------------------------------------------
async def test_cooldown_blocks_second_identical_command():
    container = build_container(make_settings())
    container.agent.mode = SimulatedAgent.Mode.NOOP
    await run_cycles(container, 1)

    first = ActionProposal(
        action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 30}, source="operator"
    )
    decision1, _ = await container.supervisor.submit_proposal(first)
    assert decision1.approved is True

    second = ActionProposal(
        action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 30}, source="operator"
    )
    decision2, command2 = await container.supervisor.submit_proposal(second)
    assert decision2.approved is False
    assert decision2.reason_code in ("COOLDOWN_ACTIVE", "DUPLICATE_COMMAND")
    assert command2 is None
    container.db.close()


# ---------------------------------------------------------------------------
# SAFE_LOCKDOWN halts actuator execution
# ---------------------------------------------------------------------------
async def test_lockdown_blocks_actuator_commands():
    container = build_container(make_settings())
    container.agent.mode = SimulatedAgent.Mode.NOOP
    await run_cycles(container, 1)

    await container.supervisor.trigger_lockdown("integration test fault")

    proposal = ActionProposal(
        action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 45}, source="operator"
    )
    decision, command = await container.supervisor.submit_proposal(proposal)
    assert decision.approved is False
    assert decision.reason_code == "INVALID_SYSTEM_STATE"
    assert command is None
    container.db.close()


# ---------------------------------------------------------------------------
# Forcing the simulated agent offline must genuinely degrade the system
# ---------------------------------------------------------------------------
async def test_forced_agent_offline_degrades_and_recovers():
    settings = make_settings(degraded_timeout_seconds=0.0, offline_timeout_seconds=0.0)
    container = build_container(settings)

    container.supervisor.set_agent_available(False)
    await run_cycles(container, 2)
    assert container.state_machine.current_state == SystemState.OFFLINE_LOCAL
    assert container.state_machine.controller_authority == "local"

    container.supervisor.set_agent_available(True)
    await run_cycles(container, 1)
    assert container.state_machine.current_state == SystemState.RECOVERY

    await run_cycles(container, 1)
    assert container.state_machine.current_state == SystemState.ONLINE_AGENT
    container.db.close()


# ---------------------------------------------------------------------------
# Stale commands are not executed
# ---------------------------------------------------------------------------
async def test_expired_command_is_not_executed():
    container = build_container(make_settings(command_ttl_seconds=0.0))
    container.agent.mode = SimulatedAgent.Mode.NOOP
    await run_cycles(container, 1)

    before = len(container.transport.dispatched)
    proposal = ActionProposal(
        action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 33}, source="operator"
    )
    decision, command = await container.supervisor.submit_proposal(proposal)

    assert decision.approved is True
    assert command is not None
    assert command.status == CommandStatus.FAILED
    assert command.error == "COMMAND_EXPIRED"
    # The transport must never have been asked to execute a stale command.
    assert len(container.transport.dispatched) == before
    container.db.close()


# ---------------------------------------------------------------------------
# Stale telemetry fails closed
# ---------------------------------------------------------------------------
async def test_stale_telemetry_fails_closed():
    container = build_container(make_settings(context_max_age_seconds=0.0))
    container.agent.mode = SimulatedAgent.Mode.NOOP
    await run_cycles(container, 1)
    await asyncio.sleep(0.05)  # ensure the context is older than max age

    proposal = ActionProposal(
        action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 45}, source="operator"
    )
    decision, command = await container.supervisor.submit_proposal(proposal)
    assert decision.approved is False
    assert decision.reason_code == "CONTEXT_STALE"
    assert command is None
    container.db.close()
