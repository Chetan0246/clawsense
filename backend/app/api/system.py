"""System status and state-machine endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.container import AppContainer
from app.dependencies import get_container
from app.schemas.api import ForceStateRequest
from app.schemas.system import SystemState
from app.services.state_machine import InvalidTransition

router = APIRouter(prefix="/api/v1/system", tags=["system"])

# Reason code used for operator-forced transitions.
RC_MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


@router.get("/status")
def status(container: AppContainer = Depends(get_container)) -> dict:
    return container.supervisor.status_payload()


@router.get("/state")
def state(container: AppContainer = Depends(get_container)) -> dict:
    status = container.state_machine.status()
    return {
        "current_state": status.current_state.value,
        "previous_state": status.previous_state.value if status.previous_state else None,
        "controller_authority": status.controller_authority,
        "transition_reason_code": status.transition_reason_code,
        "transition_reason": status.transition_reason,
        "last_transition_at": status.last_transition_at,
        "recovery_status": status.recovery_status,
    }


@router.get("/transitions")
def transitions(
    limit: int = Query(50, ge=1, le=500),
    container: AppContainer = Depends(get_container),
) -> dict:
    items = container.transition_repo.list(limit=limit)
    return {"items": [t.model_dump(mode="json") for t in items], "total": len(items)}


@router.post("/state")
async def force_state(
    request: ForceStateRequest,
    container: AppContainer = Depends(get_container),
) -> dict:
    try:
        new_state = SystemState(request.state)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown state: {request.state}")
    try:
        transition = await container.supervisor.force_state(
            new_state, request.reason_code or RC_MANUAL_OVERRIDE, request.reason
        )
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return transition.model_dump(mode="json")


@router.post("/lockdown")
async def lockdown(
    reason: str = Query("Operator-initiated safe lockdown."),
    container: AppContainer = Depends(get_container),
) -> dict:
    try:
        transition = await container.supervisor.trigger_lockdown(reason)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return transition.model_dump(mode="json")


@router.post("/reset")
async def reset(container: AppContainer = Depends(get_container)) -> dict:
    try:
        transition = await container.supervisor.reset_lockdown()
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return transition.model_dump(mode="json")
