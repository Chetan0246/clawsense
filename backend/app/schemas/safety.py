"""Safety-check and safety-decision schemas (PLAN.md section 10)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


#: Canonical ordering of safety checks, matching PLAN.md section 10.
CHECK_ORDER: tuple[str, ...] = (
    "schema",
    "allow_list",
    "parameter_types",
    "range",
    "context_freshness",
    "system_state",
    "cooldown",
    "duplicate",
)


class CheckResult(BaseModel):
    """Outcome of one independent safety check."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: CheckStatus
    detail: str = ""
    #: Machine-readable reason code when this check fails (``None`` otherwise).
    code: str | None = None
    timestamp: datetime = Field(default_factory=_utcnow)
    proposal_id: str | None = None


class SafetyResult(BaseModel):
    """Deterministic safety decision.

    ``checks`` is a compact ``name -> status`` map (PLAN.md section 10 example).
    ``check_results`` carries the full per-check detail used by the Safety
    Center page.
    """

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    proposal_id: str
    approved: bool
    reason_code: str
    reason: str
    checks: dict[str, str] = Field(default_factory=dict)
    check_results: list[CheckResult] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_utcnow)
    dispatch_attempted: bool = False
