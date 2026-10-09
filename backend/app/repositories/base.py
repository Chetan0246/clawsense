"""Shared serialization helpers for repositories."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def iso(dt: datetime | None) -> str | None:
    """Serialize a datetime to an ISO-8601 UTC string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string back into a datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def dumps(value: Any) -> str:
    """Deterministic JSON serialization."""
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default
