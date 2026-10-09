"""Deterministic safety supervisor tests (PLAN.md section 7 test cases)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas.actions import ActionName, ActionProposal
from app.schemas.system import SystemState
from app.services.safety_supervisor import (
    RC_ANGLE_OUT_OF_RANGE,
    RC_APPROVED,
    RC_CONTEXT_MISSING,
    RC_CONTEXT_STALE,
    RC_COOLDOWN_ACTIVE,
    RC_DUPLICATE_COMMAND,
    RC_DURATION_OUT_OF_RANGE,
    RC_INVALID_PARAMETERS,
    RC_INVALID_SYSTEM_STATE,
    RC_SCHEMA_INVALID,
    RC_UNKNOWN_ACTION,
    SafetySupervisor,
)
from tests.conftest import fresh_context, make_settings

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_UNSET = object()


def supervisor(**overrides) -> SafetySupervisor:
    return SafetySupervisor(make_settings(**overrides))


def validate(proposal, *, context=_UNSET, state=SystemState.ONLINE_AGENT, sup=None, now=NOW):
    sup = sup or supervisor()
    if context is _UNSET:
        context = fresh_context(now=now)
    return sup.validate(proposal, state, context, now=now)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_valid_servo_command_is_approved():
    result = validate(
        ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 90})
    )
    assert result.approved is True
    assert result.reason_code == RC_APPROVED
    assert all(status != "FAIL" for status in result.checks.values())
    assert result.dispatch_attempted is False  # supervisor never dispatches


def test_no_op_is_approved_without_context():
    result = validate(
        ActionProposal(action=ActionName.NO_OP, parameters={}), context=None
    )
    assert result.approved is True


# ---------------------------------------------------------------------------
# Range failures
# ---------------------------------------------------------------------------
def test_servo_angle_250_is_rejected_by_range():
    result = validate(
        ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 250})
    )
    assert result.approved is False
    assert result.reason_code == RC_ANGLE_OUT_OF_RANGE
    # Per PLAN.md: schema PASS, allow-list PASS, range FAIL.
    assert result.checks["schema"] == "PASS"
    assert result.checks["allow_list"] == "PASS"
    assert result.checks["range"] == "FAIL"
    assert result.dispatch_attempted is False


def test_servo_negative_angle_is_rejected():
    result = validate(
        ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": -5})
    )
    assert result.approved is False
    assert result.reason_code == RC_ANGLE_OUT_OF_RANGE


def test_servo_boundary_values_are_accepted():
    for angle in (0, 180):
        result = validate(
            ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": angle})
        )
        assert result.approved is True, angle


def test_buzzer_duration_out_of_range_is_rejected():
    result = validate(
        ActionProposal(action=ActionName.BUZZER_BEEP, parameters={"duration_ms": 99999})
    )
    assert result.approved is False
    assert result.reason_code == RC_DURATION_OUT_OF_RANGE


# ---------------------------------------------------------------------------
# Schema / allow-list / parameter failures
# ---------------------------------------------------------------------------
def test_unknown_action_is_rejected():
    payload = {
        "proposal_id": "p-unknown",
        "action": "fly_drone",
        "parameters": {},
        "source": "agent",
    }
    result = validate(payload)
    assert result.approved is False
    assert result.reason_code == RC_UNKNOWN_ACTION
    assert result.checks["allow_list"] == "FAIL"


def test_non_object_payload_is_rejected():
    result = validate("this is not a proposal")
    assert result.approved is False
    assert result.reason_code == RC_SCHEMA_INVALID


def test_missing_required_fields_are_rejected():
    result = validate({"action": "servo_move"})
    assert result.approved is False
    assert result.reason_code == RC_SCHEMA_INVALID


def test_wrong_parameter_type_is_rejected():
    payload = {
        "proposal_id": "p-type",
        "action": "servo_move",
        "parameters": {"angle_degrees": "ninety"},
        "source": "agent",
    }
    result = validate(payload)
    assert result.approved is False
    assert result.reason_code == RC_INVALID_PARAMETERS
    assert result.checks["parameter_types"] == "FAIL"


def test_missing_parameter_is_rejected():
    payload = {
        "proposal_id": "p-missing",
        "action": "servo_move",
        "parameters": {},
        "source": "agent",
    }
    result = validate(payload)
    assert result.approved is False
    assert result.reason_code == RC_INVALID_PARAMETERS


def test_unknown_extra_parameter_is_rejected():
    payload = {
        "proposal_id": "p-extra",
        "action": "servo_move",
        "parameters": {"angle_degrees": 90, "torque": 100},
        "source": "agent",
    }
    result = validate(payload)
    assert result.approved is False
    assert result.reason_code == RC_INVALID_PARAMETERS


def test_invalid_led_color_is_rejected():
    result = validate(
        ActionProposal(action=ActionName.SET_STATUS_LED, parameters={"color": "purple"})
    )
    assert result.approved is False
    assert result.reason_code == RC_INVALID_PARAMETERS


# ---------------------------------------------------------------------------
# Context freshness
# ---------------------------------------------------------------------------
def test_stale_context_is_rejected():
    context = fresh_context(now=NOW, age_seconds=120)
    result = validate(
        ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 90}),
        context=context,
    )
    assert result.approved is False
    assert result.reason_code == RC_CONTEXT_STALE


def test_missing_context_is_rejected_for_actuator_action():
    result = validate(
        ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 90}),
        context=None,
    )
    assert result.approved is False
    assert result.reason_code == RC_CONTEXT_MISSING


# ---------------------------------------------------------------------------
# System state
# ---------------------------------------------------------------------------
def test_safe_lockdown_rejects_all_actions():
    result = validate(
        ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 90}),
        state=SystemState.SAFE_LOCKDOWN,
    )
    assert result.approved is False
    assert result.reason_code == RC_INVALID_SYSTEM_STATE


def test_agent_proposal_rejected_in_offline_local_state():
    result = validate(
        ActionProposal(
            action=ActionName.SERVO_MOVE,
            parameters={"angle_degrees": 90},
            source="agent",
        ),
        state=SystemState.OFFLINE_LOCAL,
    )
    assert result.approved is False
    assert result.reason_code == RC_INVALID_SYSTEM_STATE


def test_fallback_proposal_allowed_in_offline_local_state():
    result = validate(
        ActionProposal(
            action=ActionName.SERVO_MOVE,
            parameters={"angle_degrees": 45},
            source="fallback",
        ),
        state=SystemState.OFFLINE_LOCAL,
    )
    assert result.approved is True


# ---------------------------------------------------------------------------
# Cooldown and duplicate
# ---------------------------------------------------------------------------
def test_cooldown_blocks_rapid_repeat():
    context = fresh_context(now=NOW)
    context.record_action("servo_move", {"angle_degrees": 90}, timestamp=NOW)
    result = validate(
        ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 90}),
        context=context,
        now=NOW + timedelta(seconds=1),
    )
    assert result.approved is False
    # Both cooldown and duplicate should fire for an identical repeat.
    assert result.checks["cooldown"] == "FAIL"
    assert result.checks["duplicate"] == "FAIL"
    assert result.reason_code in (RC_COOLDOWN_ACTIVE, RC_DUPLICATE_COMMAND)


def test_cooldown_allows_repeat_after_window():
    context = fresh_context(now=NOW)
    context.record_action("servo_move", {"angle_degrees": 90}, timestamp=NOW)
    result = validate(
        ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 90}),
        context=context,
        now=NOW + timedelta(seconds=10),
    )
    assert result.approved is True


def test_different_parameters_are_not_duplicates():
    context = fresh_context(now=NOW)
    context.record_action("servo_move", {"angle_degrees": 90}, timestamp=NOW)
    result = validate(
        ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 120}),
        context=context,
        now=NOW + timedelta(seconds=10),
    )
    assert result.approved is True


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_validation_is_deterministic():
    sup = supervisor()
    proposal = ActionProposal(
        action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 250}
    )
    first = sup.validate(proposal, SystemState.ONLINE_AGENT, fresh_context(now=NOW), now=NOW)
    second = sup.validate(proposal, SystemState.ONLINE_AGENT, fresh_context(now=NOW), now=NOW)
    assert first.checks == second.checks
    assert first.approved == second.approved
    assert first.reason_code == second.reason_code


def test_every_check_is_reported():
    result = validate(
        ActionProposal(action=ActionName.SERVO_MOVE, parameters={"angle_degrees": 90})
    )
    expected = {
        "schema",
        "allow_list",
        "parameter_types",
        "range",
        "context_freshness",
        "system_state",
        "cooldown",
        "duplicate",
    }
    assert set(result.checks) == expected
    assert len(result.check_results) == len(expected)
