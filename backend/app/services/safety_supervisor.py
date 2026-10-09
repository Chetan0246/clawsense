"""ClawSense Deterministic Safety Supervisor (PLAN.md section 10).

This module has **no dependency on the LLM**.  It validates every actuator
proposal against a fixed, allow-listed action contract and a set of explicit,
independently reported checks.  Validation is deterministic: identical inputs
and configuration always produce the identical decision.

Safety philosophy:
* Fail closed.  Unknown or malformed input is rejected.
* Missing safety-critical context is rejected.
* The LLM can never invent an action name or operate a GPIO directly.
* A software approval is NOT proof of physical safety; firmware re-validates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.config import Settings
from app.schemas.actions import (
    ACTION_PARAM_SCHEMAS,
    ActionName,
    BuzzerParams,
    ServoParams,
)
from app.schemas.safety import CheckResult, CheckStatus, SafetyResult
from app.schemas.system import SystemState
from app.services.context_memory import ContextMemory

# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------
RC_APPROVED = "APPROVED"
RC_SCHEMA_INVALID = "SCHEMA_INVALID"
RC_UNKNOWN_ACTION = "UNKNOWN_ACTION"
RC_INVALID_PARAMETERS = "INVALID_PARAMETERS"
RC_ANGLE_OUT_OF_RANGE = "ANGLE_OUT_OF_RANGE"
RC_DURATION_OUT_OF_RANGE = "DURATION_OUT_OF_RANGE"
RC_CONTEXT_MISSING = "CONTEXT_MISSING"
RC_CONTEXT_STALE = "CONTEXT_STALE"
RC_INVALID_SYSTEM_STATE = "INVALID_SYSTEM_STATE"
RC_COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
RC_DUPLICATE_COMMAND = "DUPLICATE_COMMAND"

#: Actions that require fresh sensor context before they may execute.
CONTEXT_DEPENDENT_ACTIONS = {ActionName.SERVO_MOVE, ActionName.BUZZER_BEEP}

#: Which sources may drive actuators in each state.
_STATE_SOURCE_RULES: dict[SystemState, set[str]] = {
    SystemState.ONLINE_AGENT: {"agent", "fallback", "operator", "simulator"},
    SystemState.DEGRADED: {"agent", "fallback", "operator", "simulator"},
    SystemState.OFFLINE_LOCAL: {"fallback", "operator", "simulator"},
    SystemState.RECOVERY: {"fallback", "operator", "simulator"},
    SystemState.SAFE_LOCKDOWN: set(),
}

_REQUIRED_FIELDS = ("proposal_id", "action", "parameters", "source")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SafetySupervisor:
    """Deterministic validation of actuator proposals."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # -- public API --------------------------------------------------------
    def validate(
        self,
        proposal: Any,
        system_state: SystemState,
        context: ContextMemory | None,
        *,
        now: datetime | None = None,
    ) -> SafetyResult:
        """Validate ``proposal`` and return a :class:`SafetyResult`.

        ``proposal`` may be an already-parsed mapping/object or a raw dict
        (including a malformed one).  All checks are evaluated and reported
        independently.
        """
        now = now or _utcnow()
        checks: list[CheckResult] = []

        raw = self._as_mapping(proposal)
        proposal_id = self._extract_proposal_id(proposal, raw)

        # 1. Schema -------------------------------------------------------
        schema_check, action_str, parameters, source = self._check_schema(
            proposal_id, raw
        )
        checks.append(schema_check)

        # 2. Allow-list ---------------------------------------------------
        allow_check, action = self._check_allow_list(proposal_id, action_str)
        checks.append(allow_check)

        # 3. Parameter types ---------------------------------------------
        type_check = self._check_parameter_types(proposal_id, action, parameters)
        checks.append(type_check)

        # 4. Numeric ranges ----------------------------------------------
        range_check = self._check_range(proposal_id, action, parameters)
        checks.append(range_check)

        # 5. Context freshness -------------------------------------------
        checks.append(
            self._check_context_freshness(proposal_id, action, context, now)
        )

        # 6. System state -------------------------------------------------
        checks.append(
            self._check_system_state(proposal_id, source, system_state)
        )

        # 7. Cooldown -----------------------------------------------------
        checks.append(self._check_cooldown(proposal_id, action, context, now))

        # 8. Duplicate / conflicting command ------------------------------
        checks.append(
            self._check_duplicate(proposal_id, action, parameters, context, now)
        )

        approved = all(c.status != CheckStatus.FAIL for c in checks)
        first_fail = next((c for c in checks if c.status == CheckStatus.FAIL), None)

        if approved:
            reason_code = RC_APPROVED
            reason = "All safety checks passed."
        else:
            reason_code = self._reason_code_for(first_fail, action)
            reason = first_fail.detail if first_fail else "Rejected by safety policy."

        return SafetyResult(
            proposal_id=proposal_id,
            approved=approved,
            reason_code=reason_code,
            reason=reason,
            checks={c.name: c.status.value for c in checks},
            check_results=checks,
            timestamp=now,
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _as_mapping(proposal: Any) -> dict[str, Any] | None:
        if proposal is None:
            return None
        if isinstance(proposal, dict):
            return proposal
        if hasattr(proposal, "model_dump"):
            try:
                return proposal.model_dump(mode="json")
            except Exception:  # pragma: no cover - defensive
                return None
        if hasattr(proposal, "__dict__"):
            return dict(proposal.__dict__)
        return None

    @staticmethod
    def _extract_proposal_id(proposal: Any, raw: dict | None) -> str:
        if isinstance(raw, dict):
            pid = raw.get("proposal_id")
            if isinstance(pid, str) and pid:
                return pid
        pid = getattr(proposal, "proposal_id", None)
        return pid if isinstance(pid, str) and pid else "unknown"

    def _check_schema(
        self, proposal_id: str, raw: dict | None
    ) -> tuple[CheckResult, str | None, dict, str]:
        """Validate structural schema.  Returns (check, action, params, source)."""
        if raw is None:
            return (
                CheckResult(
                    name="schema",
                    status=CheckStatus.FAIL,
                    detail="Proposal is not a JSON object.",
                    code=RC_SCHEMA_INVALID,
                    proposal_id=proposal_id,
                ),
                None,
                {},
                "unknown",
            )

        missing = [f for f in _REQUIRED_FIELDS if f not in raw]
        if missing:
            return (
                CheckResult(
                    name="schema",
                    status=CheckStatus.FAIL,
                    detail=f"Missing required field(s): {', '.join(missing)}.",
                    code=RC_SCHEMA_INVALID,
                    proposal_id=proposal_id,
                ),
                None,
                {},
                "unknown",
            )

        action_raw = raw.get("action")
        if not isinstance(action_raw, str) or not action_raw.strip():
            return (
                CheckResult(
                    name="schema",
                    status=CheckStatus.FAIL,
                    detail="'action' must be a non-empty string.",
                    code=RC_SCHEMA_INVALID,
                    proposal_id=proposal_id,
                ),
                None,
                {},
                "unknown",
            )

        parameters = raw.get("parameters")
        if not isinstance(parameters, dict):
            return (
                CheckResult(
                    name="schema",
                    status=CheckStatus.FAIL,
                    detail="'parameters' must be an object.",
                    code=RC_SCHEMA_INVALID,
                    proposal_id=proposal_id,
                ),
                None,
                {},
                "unknown",
            )

        source = raw.get("source", "unknown")
        if not isinstance(source, str):
            source = "unknown"

        reason = raw.get("reason", "")
        if reason is not None and not isinstance(reason, str):
            return (
                CheckResult(
                    name="schema",
                    status=CheckStatus.FAIL,
                    detail="'reason' must be a string when present.",
                    code=RC_SCHEMA_INVALID,
                    proposal_id=proposal_id,
                ),
                None,
                {},
                source,
            )

        return (
            CheckResult(
                name="schema",
                status=CheckStatus.PASS,
                detail="Required fields present with correct types.",
                proposal_id=proposal_id,
            ),
            action_raw.strip(),
            parameters,
            source,
        )

    def _check_allow_list(
        self, proposal_id: str, action_str: str | None
    ) -> tuple[CheckResult, ActionName | None]:
        if action_str is None:
            return (
                CheckResult(
                    name="allow_list",
                    status=CheckStatus.SKIP,
                    detail="Cannot evaluate allow-list without a valid action.",
                    proposal_id=proposal_id,
                ),
                None,
            )
        if action_str not in self.settings.allowed_actions:
            return (
                CheckResult(
                    name="allow_list",
                    status=CheckStatus.FAIL,
                    detail=f"Action '{action_str}' is not in the allow-list.",
                    code=RC_UNKNOWN_ACTION,
                    proposal_id=proposal_id,
                ),
                None,
            )
        try:
            action = ActionName(action_str)
        except ValueError:
            return (
                CheckResult(
                    name="allow_list",
                    status=CheckStatus.FAIL,
                    detail=f"Action '{action_str}' is not a known action.",
                    code=RC_UNKNOWN_ACTION,
                    proposal_id=proposal_id,
                ),
                None,
            )
        return (
            CheckResult(
                name="allow_list",
                status=CheckStatus.PASS,
                detail=f"Action '{action_str}' is allow-listed.",
                proposal_id=proposal_id,
            ),
            action,
        )

    def _check_parameter_types(
        self, proposal_id: str, action: ActionName | None, parameters: dict
    ) -> CheckResult:
        if action is None:
            return CheckResult(
                name="parameter_types",
                status=CheckStatus.SKIP,
                detail="Cannot evaluate parameter types without a valid action.",
                proposal_id=proposal_id,
            )
        schema = ACTION_PARAM_SCHEMAS[action]
        try:
            schema.model_validate(parameters)
        except ValidationError as exc:
            problems = []
            for err in exc.errors():
                loc = ".".join(str(p) for p in err.get("loc", ())) or "(root)"
                problems.append(f"{loc}: {err.get('msg', 'invalid')}")
            return CheckResult(
                name="parameter_types",
                status=CheckStatus.FAIL,
                detail="Invalid parameters: " + "; ".join(problems),
                code=RC_INVALID_PARAMETERS,
                proposal_id=proposal_id,
            )
        return CheckResult(
            name="parameter_types",
            status=CheckStatus.PASS,
            detail="Parameter types are valid.",
            proposal_id=proposal_id,
        )

    def _check_range(
        self, proposal_id: str, action: ActionName | None, parameters: dict
    ) -> CheckResult:
        if action is None:
            return CheckResult(
                name="range",
                status=CheckStatus.SKIP,
                detail="Cannot evaluate ranges without a valid action.",
                proposal_id=proposal_id,
            )
        if action == ActionName.SERVO_MOVE:
            angle = parameters.get("angle_degrees")
            if not isinstance(angle, int) or isinstance(angle, bool):
                return CheckResult(
                    name="range",
                    status=CheckStatus.SKIP,
                    detail="Angle not an integer; range not evaluated.",
                    proposal_id=proposal_id,
                )
            lo, hi = self.settings.servo_min_degrees, self.settings.servo_max_degrees
            if not (lo <= angle <= hi):
                return CheckResult(
                    name="range",
                    status=CheckStatus.FAIL,
                    detail=(
                        f"Servo angle {angle} is outside the allowed range "
                        f"{lo}-{hi} degrees."
                    ),
                    code=RC_ANGLE_OUT_OF_RANGE,
                    proposal_id=proposal_id,
                )
            return CheckResult(
                name="range",
                status=CheckStatus.PASS,
                detail=f"Servo angle {angle} within {lo}-{hi} degrees.",
                proposal_id=proposal_id,
            )
        if action == ActionName.BUZZER_BEEP:
            duration = parameters.get("duration_ms")
            if not isinstance(duration, int) or isinstance(duration, bool):
                return CheckResult(
                    name="range",
                    status=CheckStatus.SKIP,
                    detail="Duration not an integer; range not evaluated.",
                    proposal_id=proposal_id,
                )
            hi = self.settings.buzzer_max_ms
            if not (1 <= duration <= hi):
                return CheckResult(
                    name="range",
                    status=CheckStatus.FAIL,
                    detail=f"Buzzer duration {duration}ms outside allowed 1-{hi}ms.",
                    code=RC_DURATION_OUT_OF_RANGE,
                    proposal_id=proposal_id,
                )
            return CheckResult(
                name="range",
                status=CheckStatus.PASS,
                detail=f"Buzzer duration {duration}ms within 1-{hi}ms.",
                proposal_id=proposal_id,
            )
        return CheckResult(
            name="range",
            status=CheckStatus.PASS,
            detail="No numeric range constraints for this action.",
            proposal_id=proposal_id,
        )

    def _check_context_freshness(
        self,
        proposal_id: str,
        action: ActionName | None,
        context: ContextMemory | None,
        now: datetime,
    ) -> CheckResult:
        if action is None:
            return CheckResult(
                name="context_freshness",
                status=CheckStatus.SKIP,
                detail="Cannot evaluate context without a valid action.",
                proposal_id=proposal_id,
            )
        if action not in CONTEXT_DEPENDENT_ACTIONS:
            return CheckResult(
                name="context_freshness",
                status=CheckStatus.SKIP,
                detail="Indicator action; fresh sensor context not required.",
                proposal_id=proposal_id,
            )
        if context is None or context.telemetry is None:
            return CheckResult(
                name="context_freshness",
                status=CheckStatus.FAIL,
                detail="No sensor context available; failing closed.",
                code=RC_CONTEXT_MISSING,
                proposal_id=proposal_id,
            )
        age = context.telemetry_age_seconds(now)
        max_age = self.settings.context_max_age_seconds
        if age is None:
            return CheckResult(
                name="context_freshness",
                status=CheckStatus.FAIL,
                detail="Sensor context has no timestamp; failing closed.",
                code=RC_CONTEXT_MISSING,
                proposal_id=proposal_id,
            )
        if age > max_age:
            return CheckResult(
                name="context_freshness",
                status=CheckStatus.FAIL,
                detail=f"Context age {age:.1f}s exceeds maximum {max_age:.1f}s.",
                code=RC_CONTEXT_STALE,
                proposal_id=proposal_id,
            )
        return CheckResult(
            name="context_freshness",
            status=CheckStatus.PASS,
            detail=f"Context age {age:.1f}s within {max_age:.1f}s.",
            proposal_id=proposal_id,
        )

    def _check_system_state(
        self, proposal_id: str, source: str, system_state: SystemState
    ) -> CheckResult:
        allowed_sources = _STATE_SOURCE_RULES.get(system_state, set())
        if source not in allowed_sources:
            return CheckResult(
                name="system_state",
                status=CheckStatus.FAIL,
                detail=(
                    f"Source '{source}' may not drive actuators in state "
                    f"{system_state.value}."
                ),
                code=RC_INVALID_SYSTEM_STATE,
                proposal_id=proposal_id,
            )
        return CheckResult(
            name="system_state",
            status=CheckStatus.PASS,
            detail=f"Source '{source}' permitted in state {system_state.value}.",
            proposal_id=proposal_id,
        )

    def _check_cooldown(
        self,
        proposal_id: str,
        action: ActionName | None,
        context: ContextMemory | None,
        now: datetime,
    ) -> CheckResult:
        if action is None or context is None:
            return CheckResult(
                name="cooldown",
                status=CheckStatus.SKIP,
                detail="No action or context; cooldown not evaluated.",
                proposal_id=proposal_id,
            )
        if action == ActionName.NO_OP:
            return CheckResult(
                name="cooldown",
                status=CheckStatus.PASS,
                detail="no_op is exempt from cooldown.",
                proposal_id=proposal_id,
            )
        cooldown = self.settings.action_cooldown_seconds
        last = context.last_action_time(action.value, now=now)
        if last is not None:
            elapsed = (now - last).total_seconds()
            if elapsed < cooldown:
                return CheckResult(
                    name="cooldown",
                    status=CheckStatus.FAIL,
                    detail=(
                        f"Cooldown active for '{action.value}': "
                        f"{elapsed:.1f}s < {cooldown:.1f}s."
                    ),
                    code=RC_COOLDOWN_ACTIVE,
                    proposal_id=proposal_id,
                )
        return CheckResult(
            name="cooldown",
            status=CheckStatus.PASS,
            detail="No active cooldown for this action.",
            proposal_id=proposal_id,
        )

    def _check_duplicate(
        self,
        proposal_id: str,
        action: ActionName | None,
        parameters: dict,
        context: ContextMemory | None,
        now: datetime,
    ) -> CheckResult:
        if action is None or context is None:
            return CheckResult(
                name="duplicate",
                status=CheckStatus.SKIP,
                detail="No action or context; duplicate not evaluated.",
                proposal_id=proposal_id,
            )
        window = self.settings.action_cooldown_seconds
        dup = context.find_duplicate(action.value, parameters, window, now=now)
        if dup is not None:
            return CheckResult(
                name="duplicate",
                status=CheckStatus.FAIL,
                detail=(
                    f"Identical '{action.value}' command already issued within "
                    f"{window:.1f}s."
                ),
                code=RC_DUPLICATE_COMMAND,
                proposal_id=proposal_id,
            )
        return CheckResult(
            name="duplicate",
            status=CheckStatus.PASS,
            detail="No duplicate command detected.",
            proposal_id=proposal_id,
        )

    @staticmethod
    def _reason_code_for(
        check: CheckResult | None, action: ActionName | None = None
    ) -> str:
        if check is None:
            return RC_SCHEMA_INVALID
        if check.code:
            return check.code
        # Fallback mapping if a check failed without an explicit code.
        if check.name == "range" and action == ActionName.BUZZER_BEEP:
            return RC_DURATION_OUT_OF_RANGE
        return {
            "schema": RC_SCHEMA_INVALID,
            "allow_list": RC_UNKNOWN_ACTION,
            "parameter_types": RC_INVALID_PARAMETERS,
            "range": RC_ANGLE_OUT_OF_RANGE,
            "context_freshness": RC_CONTEXT_MISSING,
            "system_state": RC_INVALID_SYSTEM_STATE,
            "cooldown": RC_COOLDOWN_ACTIVE,
            "duplicate": RC_DUPLICATE_COMMAND,
        }.get(check.name, RC_SCHEMA_INVALID)
