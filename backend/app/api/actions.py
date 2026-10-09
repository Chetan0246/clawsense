"""Action proposal and command endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.container import AppContainer
from app.dependencies import get_container
from app.schemas.actions import ActionProposal
from app.schemas.api import ProposalRequest

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])


@router.post("/propose")
async def propose(
    request: ProposalRequest,
    container: AppContainer = Depends(get_container),
) -> dict:
    """Submit an operator proposal.

    Well-formed proposals are validated by the deterministic supervisor.  A
    malformed proposal (unknown action / invalid parameter shape) is rejected
    at the API boundary with 422.
    """
    try:
        proposal = ActionProposal(
            action=request.action,
            parameters=request.parameters,
            reason=request.reason,
            source="operator",
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    decision, command = await container.supervisor.submit_proposal(proposal)
    return {
        "proposal": proposal.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
        "command": command.model_dump(mode="json") if command else None,
    }


@router.get("/proposals")
def proposals(
    limit: int = Query(50, ge=1, le=500),
    container: AppContainer = Depends(get_container),
) -> dict:
    items = container.proposal_repo.list(limit=limit)
    return {"items": [p.model_dump(mode="json") for p in items], "total": len(items)}


@router.get("/commands")
def commands(
    limit: int = Query(50, ge=1, le=500),
    container: AppContainer = Depends(get_container),
) -> dict:
    items = container.command_repo.list(limit=limit)
    return {"items": [c.model_dump(mode="json") for c in items], "total": len(items)}


@router.get("/commands/{command_id}")
def get_command(
    command_id: str, container: AppContainer = Depends(get_container)
) -> dict:
    command = container.command_repo.get(command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found")
    return command.model_dump(mode="json")


@router.get("/latest")
def latest(container: AppContainer = Depends(get_container)) -> dict:
    decision = container.supervisor.latest_decision or container.decision_repo.latest()
    command = container.supervisor.latest_command or container.command_repo.latest()
    return {
        "decision": decision.model_dump(mode="json") if decision else None,
        "command": command.model_dump(mode="json") if command else None,
    }
