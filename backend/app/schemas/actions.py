"""Structured action contract (PLAN.md section 9).

Every agent / fallback proposal is expressed with a strict, allow-listed
schema.  Unknown action names and unknown parameters are rejected before any
safety check runs.  The LLM never operates GPIO directly and cannot invent new
action names.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActionName(str, Enum):
    """Explicit allow-list of supported actions."""

    SERVO_MOVE = "servo_move"
    BUZZER_BEEP = "buzzer_beep"
    SET_STATUS_LED = "set_status_led"
    NO_OP = "no_op"


class LedColor(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    OFF = "off"


class ServoParams(BaseModel):
    """Parameters for ``servo_move``. Logical 0-180 range; real limits are
    enforced by the deterministic supervisor and independently by firmware."""

    model_config = ConfigDict(extra="forbid")

    angle_degrees: int = Field(..., description="Target angle in degrees")


class BuzzerParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_ms: int = Field(..., description="Beep duration in milliseconds")


class LedState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color: LedColor = Field(..., description="Target status LED colour")


class NoOpParams(BaseModel):
    """``no_op`` takes no parameters."""

    model_config = ConfigDict(extra="forbid")


#: Maps an allow-listed action to its parameter schema.
ACTION_PARAM_SCHEMAS: dict[ActionName, type[BaseModel]] = {
    ActionName.SERVO_MOVE: ServoParams,
    ActionName.BUZZER_BEEP: BuzzerParams,
    ActionName.SET_STATUS_LED: LedState,
    ActionName.NO_OP: NoOpParams,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActionProposal(BaseModel):
    """A structured action proposal.

    This is a *proposal* only.  It is never proof that an action is safe or was
    executed; it must pass the deterministic safety supervisor first.
    """

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action: ActionName
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=1000)
    source: Literal["agent", "fallback", "operator", "simulator"] = "agent"
    created_at: datetime = Field(default_factory=_utcnow)

    @field_validator("reason")
    @classmethod
    def _bound_reason(cls, value: str) -> str:
        # Optional bounded explanation: hard cap regardless of caller.
        return value[:1000]

    def parsed_parameters(self) -> BaseModel:
        """Return the typed parameter model for this proposal.

        Raises ``ValueError`` for an unknown action or invalid parameters.
        """
        schema = ACTION_PARAM_SCHEMAS.get(self.action)
        if schema is None:
            raise ValueError(f"Unknown action: {self.action}")
        return schema.model_validate(self.parameters)
