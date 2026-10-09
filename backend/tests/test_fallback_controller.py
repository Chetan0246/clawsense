"""Fallback controller tests (PLAN.md section 12)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.actions import ActionName
from app.schemas.system import SystemState
from app.services.fallback_controller import FallbackController
from app.services.safety_supervisor import SafetySupervisor
from tests.conftest import fresh_context, make_settings

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def controller(**overrides) -> FallbackController:
    return FallbackController(make_settings(**overrides))


def test_high_temperature_triggers_alert_led_and_buzzer():
    proposals = controller().evaluate(fresh_context(now=NOW, temperature=41.0))
    actions = [p.action for p in proposals]
    assert ActionName.SET_STATUS_LED in actions
    assert ActionName.BUZZER_BEEP in actions
    led = next(p for p in proposals if p.action == ActionName.SET_STATUS_LED)
    assert led.parameters["color"] == "red"
    assert all(p.source == "fallback" for p in proposals)


def test_low_temperature_triggers_caution_led():
    proposals = controller().evaluate(fresh_context(now=NOW, temperature=1.0))
    assert len(proposals) == 1
    assert proposals[0].action == ActionName.SET_STATUS_LED
    assert proposals[0].parameters["color"] == "yellow"


def test_high_humidity_triggers_caution_led():
    proposals = controller().evaluate(fresh_context(now=NOW, humidity=90.0))
    assert proposals[0].action == ActionName.SET_STATUS_LED
    assert proposals[0].parameters["color"] == "yellow"


def test_motion_triggers_observation_servo():
    proposals = controller().evaluate(fresh_context(now=NOW, motion=True))
    assert proposals[0].action == ActionName.SERVO_MOVE
    assert proposals[0].parameters["angle_degrees"] == 45


def test_nominal_conditions_produce_no_op():
    proposals = controller().evaluate(
        fresh_context(now=NOW, temperature=24.0, humidity=50.0, motion=False)
    )
    assert proposals[0].action == ActionName.NO_OP


def test_fallback_without_context_is_safe():
    # No context -> treat as nominal; never invent actuator commands.
    proposals = controller().evaluate(None)
    assert proposals[0].action == ActionName.NO_OP


def test_fallback_proposals_pass_safety_in_offline_state():
    settings = make_settings()
    proposals = controller().evaluate(fresh_context(now=NOW, temperature=41.0))
    sup = SafetySupervisor(settings)
    context = fresh_context(now=NOW, temperature=41.0)
    for proposal in proposals:
        result = sup.validate(
            proposal, SystemState.OFFLINE_LOCAL, context, now=NOW
        )
        assert result.approved is True, (proposal.action, result.reason_code)


def test_fallback_motion_respects_servo_limits():
    settings = make_settings(servo_max_degrees=30)
    proposals = FallbackController(settings).evaluate(fresh_context(now=NOW, motion=True))
    assert proposals[0].parameters["angle_degrees"] == 30
