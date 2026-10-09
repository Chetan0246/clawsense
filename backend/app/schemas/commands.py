"""Command lifecycle schemas (PLAN.md section 15).

An approved backend action is NOT equivalent to a successful device action.
Each stage is tracked independently.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CommandStatus(str, Enum):
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    DISPATCHED = "DISPATCHED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    STATE_CONFIRMED = "STATE_CONFIRMED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    UNCERTAIN = "UNCERTAIN"


class CommandRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    proposal_id: str
    decision_id: str
    target_device: str
    action: str
    parameters: dict = Field(default_factory=dict)
    status: CommandStatus = CommandStatus.PROPOSED
    dispatched_at: datetime | None = None
    acknowledged_at: datetime | None = None
    #: After this instant the command must not be executed (stale-command guard).
    expires_at: datetime | None = None
    error: str | None = None
    simulated: bool = False
    created_at: datetime = Field(default_factory=_utcnow)
