"""Safety inspection endpoints.

Exposes the deterministic supervisor's decisions.  ``POST /safety/validate``
performs a **dry run**: it validates a raw payload and returns the decision
without ever dispatching a command.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.container import AppContainer
from app.dependencies import get_container
from app.services.safety_tests import run_predefined_tests

router = APIRouter(prefix="/api/v1/safety", tags=["safety"])


@router.post("/test")
def run_safety_tests(
    container: AppContainer = Depends(get_container),
) -> dict:
    """Run the predefined safety tests against the real supervisor.

    These are **software validation tests**. They are not a hardware test and
    must not be presented as evidence of physical safety.
    """
    report = run_predefined_tests(container.settings)
    return {
        "kind": "software_validation",
        "hardware_tested": False,
        "total": len(report),
        "passed": sum(1 for item in report if item["passed"]),
        "results": report,
    }


@router.get("/events")
def safety_events(
    limit: int = Query(100, ge=1, le=500),
    container: AppContainer = Depends(get_container),
) -> dict:
    """Safety-related audit events (approvals and rejections)."""
    items: list = []
    for category in ("safety_approval", "safety_rejection"):
        batch, _ = container.event_repo.query(category=category, limit=limit)
        items.extend(batch)
    items.sort(key=lambda event: event.timestamp, reverse=True)
    items = items[:limit]
    return {"items": [e.model_dump(mode="json") for e in items], "total": len(items)}


@router.get("/latest")
def latest(container: AppContainer = Depends(get_container)) -> dict:
    decision = container.supervisor.latest_decision or container.decision_repo.latest()
    if decision is None:
        return {"available": False}
    payload = decision.model_dump(mode="json")
    payload["available"] = True
    return payload


@router.get("/decisions")
def decisions(
    limit: int = Query(50, ge=1, le=500),
    container: AppContainer = Depends(get_container),
) -> dict:
    items = container.decision_repo.list(limit=limit)
    return {"items": [d.model_dump(mode="json") for d in items], "total": len(items)}


@router.get("/decisions/{decision_id}")
def get_decision(
    decision_id: str, container: AppContainer = Depends(get_container)
) -> dict:
    decision = container.decision_repo.get(decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision.model_dump(mode="json")


@router.post("/validate")
def validate(
    payload: dict[str, Any] = Body(...),
    container: AppContainer = Depends(get_container),
) -> dict:
    """Validate a raw proposal payload without dispatching anything."""
    result = container.supervisor.safety.validate(
        payload, container.state_machine.current_state, container.supervisor.context
    )
    return result.model_dump(mode="json")
