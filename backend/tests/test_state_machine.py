"""State machine tests (PLAN.md section 11)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.system import SystemState
from app.services.state_machine import (
    RC_AGENT_RECOVERED,
    RC_AGENT_UNREACHABLE,
    RC_AGENT_UNREACHABLE_PERSISTENT,
    RC_CONNECTIVITY_RESTORED,
    RC_CRITICAL_FAULT,
    RC_FAULT_CLEARED,
    RC_RECOVERY_COMPLETED,
    InvalidTransition,
    SystemStateMachine,
)
from tests.conftest import make_settings

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def machine(**overrides) -> SystemStateMachine:
    sm = SystemStateMachine(settings=make_settings(**overrides))
    sm.last_successful_agent_request = BASE
    return sm


def test_initial_state_is_online_agent():
    sm = machine()
    assert sm.current_state == SystemState.ONLINE_AGENT
    assert sm.controller_authority == "agent"


def test_legal_transition_is_applied():
    sm = machine()
    transition = sm.request_transition(
        SystemState.DEGRADED, RC_AGENT_UNREACHABLE, "slow", now=BASE
    )
    assert transition.previous_state == SystemState.ONLINE_AGENT
    assert transition.new_state == SystemState.DEGRADED
    assert sm.current_state == SystemState.DEGRADED
    assert sm.previous_state == SystemState.ONLINE_AGENT


def test_illegal_transition_is_refused():
    sm = machine()
    with pytest.raises(InvalidTransition):
        sm.request_transition(SystemState.OFFLINE_LOCAL, RC_AGENT_UNREACHABLE, "skip")
    assert sm.current_state == SystemState.ONLINE_AGENT


def test_identical_transition_is_refused():
    sm = machine()
    with pytest.raises(InvalidTransition):
        sm.request_transition(SystemState.ONLINE_AGENT, RC_AGENT_RECOVERED)


def test_agent_failure_degrades_then_goes_offline():
    sm = machine()
    sm.on_agent_failure()

    assert sm.evaluate(now=BASE + timedelta(seconds=5)) is None
    assert sm.current_state == SystemState.ONLINE_AGENT

    t1 = sm.evaluate(now=BASE + timedelta(seconds=11))
    assert t1 is not None and t1.new_state == SystemState.DEGRADED
    assert t1.reason_code == RC_AGENT_UNREACHABLE

    t2 = sm.evaluate(now=BASE + timedelta(seconds=21))
    assert t2 is not None and t2.new_state == SystemState.OFFLINE_LOCAL
    assert t2.reason_code == RC_AGENT_UNREACHABLE_PERSISTENT
    assert sm.controller_authority == "local"


def test_offline_local_recovers_through_recovery_to_online():
    sm = machine()
    sm.on_agent_failure()
    sm.evaluate(now=BASE + timedelta(seconds=11))  # DEGRADED
    sm.evaluate(now=BASE + timedelta(seconds=21))  # OFFLINE_LOCAL
    assert sm.current_state == SystemState.OFFLINE_LOCAL

    sm.on_agent_success(now=BASE + timedelta(seconds=30))
    t = sm.evaluate(now=BASE + timedelta(seconds=30))
    assert t is not None and t.new_state == SystemState.RECOVERY
    assert t.reason_code == RC_CONNECTIVITY_RESTORED
    assert sm.recovery_status == "in_progress"

    t2 = sm.evaluate(now=BASE + timedelta(seconds=31))
    assert t2 is not None and t2.new_state == SystemState.ONLINE_AGENT
    assert t2.reason_code == RC_RECOVERY_COMPLETED
    assert sm.recovery_status == "complete"


def test_recovery_falls_back_when_health_fails():
    sm = machine()
    sm.request_transition(SystemState.DEGRADED, RC_AGENT_UNREACHABLE, "", now=BASE)
    sm.request_transition(SystemState.OFFLINE_LOCAL, RC_AGENT_UNREACHABLE_PERSISTENT, "", now=BASE)
    sm.request_transition(SystemState.RECOVERY, RC_CONNECTIVITY_RESTORED, "", now=BASE)

    sm.on_agent_failure()
    t = sm.evaluate(now=BASE + timedelta(seconds=1))
    assert t is not None and t.new_state == SystemState.OFFLINE_LOCAL


def test_lockdown_and_reset():
    sm = machine()
    t = sm.trigger_lockdown(reason="over-temperature critical fault", now=BASE)
    assert t.new_state == SystemState.SAFE_LOCKDOWN
    assert t.reason_code == RC_CRITICAL_FAULT
    assert sm.controller_authority == "none"

    # No automatic exit from lockdown.
    assert sm.evaluate(now=BASE + timedelta(seconds=1000)) is None

    t2 = sm.request_transition(
        SystemState.RECOVERY, RC_FAULT_CLEARED, "operator reset", now=BASE
    )
    assert t2.new_state == SystemState.RECOVERY


def test_degraded_recovers_quickly_to_online():
    sm = machine()
    sm.on_agent_failure()
    sm.evaluate(now=BASE + timedelta(seconds=11))
    assert sm.current_state == SystemState.DEGRADED

    sm.on_agent_success(now=BASE + timedelta(seconds=12))
    t = sm.evaluate(now=BASE + timedelta(seconds=12))
    assert t is not None and t.new_state == SystemState.ONLINE_AGENT
    assert t.reason_code == RC_AGENT_RECOVERED


def test_status_reflects_state():
    sm = machine()
    status = sm.status(now=BASE)
    assert status.current_state == SystemState.ONLINE_AGENT
    assert status.controller_authority == "agent"
    assert status.simulated is True
