"""Local deterministic fallback controller (PLAN.md section 5.6 / 12).

When the AI service or network is unavailable, control falls back to this
controller.  It is **independent of the LLM**, uses only local rules and the
last known safe sensor state, and produces proposals that are still validated
by the same deterministic safety supervisor before execution.

Documented rules (exactly two safety-relevant behaviours plus a nominal case):

    R1 HIGH_TEMPERATURE : temperature_c > temp_high_c
                          -> status LED red + short buzzer alert
    R2 LOW_TEMPERATURE  : temperature_c < temp_low_c
                          -> status LED yellow
    R3 HIGH_HUMIDITY    : humidity_percent > humidity_high_percent
                          -> status LED yellow
    R4 MOTION           : motion == true
                          -> servo to 45 degrees (observation position)
    R0 NOMINAL          : otherwise -> no_op

Every rule is bounded by the same limits enforced by the supervisor, so a
fallback action can never exceed the actuator's safe range.
"""

from __future__ import annotations

from app.config import Settings
from app.schemas.actions import ActionName, ActionProposal
from app.services.context_memory import ContextMemory

# Rule identifiers (also used as reason codes in the audit log).
RULE_NOMINAL = "FALLBACK_NOMINAL"
RULE_HIGH_TEMPERATURE = "FALLBACK_HIGH_TEMPERATURE"
RULE_LOW_TEMPERATURE = "FALLBACK_LOW_TEMPERATURE"
RULE_HIGH_HUMIDITY = "FALLBACK_HIGH_HUMIDITY"
RULE_MOTION = "FALLBACK_MOTION"


class FallbackController:
    """Deterministic rule-based controller used in OFFLINE_LOCAL mode."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _reading(self, context: ContextMemory | None, sensor: str):
        if context is None:
            return None
        reading = context.reading(sensor)
        if reading is None or reading.value is None:
            return None
        return reading.value

    def evaluate(self, context: ContextMemory | None) -> list[ActionProposal]:
        """Return the ordered list of fallback proposals for this context."""
        temperature = self._reading(context, "temperature_c")
        humidity = self._reading(context, "humidity_percent")
        motion = self._reading(context, "motion")

        proposals: list[ActionProposal] = []

        # R1: high temperature -> alert LED + bounded buzzer.
        if temperature is not None and temperature > self.settings.temp_high_c:
            proposals.append(
                ActionProposal(
                    action=ActionName.SET_STATUS_LED,
                    parameters={"color": "red"},
                    reason=(
                        f"[{RULE_HIGH_TEMPERATURE}] temperature {temperature}C > "
                        f"{self.settings.temp_high_c}C"
                    ),
                    source="fallback",
                )
            )
            proposals.append(
                ActionProposal(
                    action=ActionName.BUZZER_BEEP,
                    parameters={"duration_ms": min(500, self.settings.buzzer_max_ms)},
                    reason=f"[{RULE_HIGH_TEMPERATURE}] audible alert",
                    source="fallback",
                )
            )
            return proposals

        # R2: low temperature -> caution LED.
        if temperature is not None and temperature < self.settings.temp_low_c:
            proposals.append(
                ActionProposal(
                    action=ActionName.SET_STATUS_LED,
                    parameters={"color": "yellow"},
                    reason=(
                        f"[{RULE_LOW_TEMPERATURE}] temperature {temperature}C < "
                        f"{self.settings.temp_low_c}C"
                    ),
                    source="fallback",
                )
            )
            return proposals

        # R3: high humidity -> caution LED.
        if humidity is not None and humidity > self.settings.humidity_high_percent:
            proposals.append(
                ActionProposal(
                    action=ActionName.SET_STATUS_LED,
                    parameters={"color": "yellow"},
                    reason=(
                        f"[{RULE_HIGH_HUMIDITY}] humidity {humidity}% > "
                        f"{self.settings.humidity_high_percent}%"
                    ),
                    source="fallback",
                )
            )
            return proposals

        # R4: motion -> observation position (clamped to safe range).
        if motion:
            angle = max(
                self.settings.servo_min_degrees,
                min(45, self.settings.servo_max_degrees),
            )
            proposals.append(
                ActionProposal(
                    action=ActionName.SERVO_MOVE,
                    parameters={"angle_degrees": angle},
                    reason=f"[{RULE_MOTION}] motion detected; observing",
                    source="fallback",
                )
            )
            return proposals

        # R0: nominal.
        return [
            ActionProposal(
                action=ActionName.NO_OP,
                parameters={},
                reason=f"[{RULE_NOMINAL}] no fallback action required",
                source="fallback",
            )
        ]
