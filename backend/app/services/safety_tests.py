"""Predefined safety tests (PLAN.md section 7, Safety Center).

These exercise the **actual** deterministic supervisor — the same code path used
for live proposals — so the Safety Center's "Run Safety Test" button validates
real behaviour rather than mutating frontend state.

Each test runs against an isolated context so results are deterministic and
repeatable regardless of live system activity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import Settings
from app.schemas.safety import SafetyResult
from app.schemas.system import SystemState
from app.schemas.telemetry import SensorReading, SensorStatus, TelemetrySnapshot
from app.services.context_memory import ContextMemory
from app.services.safety_supervisor import (
    RC_ANGLE_OUT_OF_RANGE,
    RC_COOLDOWN_ACTIVE,
    RC_DUPLICATE_COMMAND,
    RC_INVALID_SYSTEM_STATE,
    RC_SCHEMA_INVALID,
    RC_UNKNOWN_ACTION,
    SafetySupervisor,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PredefinedTest:
    key: str
    name: str
    description: str
    payload: dict
    expected_approved: bool
    expected_reason_codes: tuple[str, ...] = ()
    state: SystemState = SystemState.ONLINE_AGENT
    seed_duplicate: bool = False
    seed_action: str = "servo_move"
    seed_parameters: dict = field(default_factory=lambda: {"angle_degrees": 90})


TESTS: tuple[PredefinedTest, ...] = (
    PredefinedTest(
        key="valid_servo_command",
        name="Valid servo command",
        description="An allow-listed servo_move within 0-180 degrees is approved.",
        payload={
            "proposal_id": "test-valid-servo",
            "action": "servo_move",
            "parameters": {"angle_degrees": 90},
            "source": "agent",
            "reason": "predefined safety test",
        },
        expected_approved=True,
    ),
    PredefinedTest(
        key="out_of_range_servo_angle",
        name="Out-of-range servo angle (250 degrees)",
        description=(
            "A servo_move of 250 degrees against the configured 0-180 range is "
            "rejected by range validation and is never dispatched."
        ),
        payload={
            "proposal_id": "test-angle-250",
            "action": "servo_move",
            "parameters": {"angle_degrees": 250},
            "source": "agent",
            "reason": "predefined safety test",
        },
        expected_approved=False,
        expected_reason_codes=(RC_ANGLE_OUT_OF_RANGE,),
    ),
    PredefinedTest(
        key="unknown_action",
        name="Unknown action",
        description="An action outside the allow-list is rejected.",
        payload={
            "proposal_id": "test-unknown-action",
            "action": "fly_drone",
            "parameters": {},
            "source": "agent",
            "reason": "predefined safety test",
        },
        expected_approved=False,
        expected_reason_codes=(RC_UNKNOWN_ACTION,),
    ),
    PredefinedTest(
        key="malformed_command",
        name="Malformed command",
        description="A payload missing required fields is rejected by schema validation.",
        payload={
            "proposal_id": "test-malformed",
            "action": "servo_move",
            # 'parameters' and 'source' deliberately missing
        },
        expected_approved=False,
        expected_reason_codes=(RC_SCHEMA_INVALID,),
    ),
    PredefinedTest(
        key="invalid_operating_state",
        name="Invalid operating state",
        description="Actuator commands are rejected while the system is in SAFE_LOCKDOWN.",
        payload={
            "proposal_id": "test-invalid-state",
            "action": "servo_move",
            "parameters": {"angle_degrees": 90},
            "source": "agent",
            "reason": "predefined safety test",
        },
        state=SystemState.SAFE_LOCKDOWN,
        expected_approved=False,
        expected_reason_codes=(RC_INVALID_SYSTEM_STATE,),
    ),
    PredefinedTest(
        key="duplicate_command",
        name="Duplicate / too-frequent command",
        description="An identical command inside the cooldown window is rejected.",
        payload={
            "proposal_id": "test-duplicate",
            "action": "servo_move",
            "parameters": {"angle_degrees": 90},
            "source": "agent",
            "reason": "predefined safety test",
        },
        expected_approved=False,
        expected_reason_codes=(RC_COOLDOWN_ACTIVE, RC_DUPLICATE_COMMAND),
        seed_duplicate=True,
    ),
)


def _fresh_context(now: datetime) -> ContextMemory:
    """A context with a fresh, healthy sensor snapshot."""
    snapshot = TelemetrySnapshot(
        device_id="safety-test",
        timestamp=now,
        simulated=True,
        readings={
            "temperature_c": SensorReading(
                sensor="temperature_c", value=24.0, unit="C",
                status=SensorStatus.OK, timestamp=now, simulated=True,
            ),
            "humidity_percent": SensorReading(
                sensor="humidity_percent", value=50.0, unit="%",
                status=SensorStatus.OK, timestamp=now, simulated=True,
            ),
            "motion": SensorReading(
                sensor="motion", value=False, unit="bool",
                status=SensorStatus.OK, timestamp=now, simulated=True,
            ),
        },
    )
    context = ContextMemory()
    context.update_telemetry(snapshot)
    return context


def run_predefined_tests(
    settings: Settings, *, now: datetime | None = None
) -> list[dict]:
    """Run every predefined test and return a JSON-serializable report."""
    now = now or _utcnow()
    supervisor = SafetySupervisor(settings)
    report: list[dict] = []

    for test in TESTS:
        context = _fresh_context(now)
        if test.seed_duplicate:
            context.record_action(
                test.seed_action, test.seed_parameters, timestamp=now
            )

        result: SafetyResult = supervisor.validate(
            test.payload, test.state, context, now=now
        )

        reason_ok = (
            not test.expected_reason_codes
            or result.reason_code in test.expected_reason_codes
        )
        passed = result.approved == test.expected_approved and reason_ok

        report.append(
            {
                "key": test.key,
                "name": test.name,
                "description": test.description,
                "payload": test.payload,
                "system_state": test.state.value,
                "expected": {
                    "approved": test.expected_approved,
                    "reason_codes": list(test.expected_reason_codes),
                },
                "result": result.model_dump(mode="json"),
                "passed": passed,
            }
        )

    return report
