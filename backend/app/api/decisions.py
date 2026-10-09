"""Decision-oriented aliases (PLAN.md section 8.1).

The plan suggests ``/decisions/propose`` and ``/decisions``. The canonical
implementation lives under ``/actions`` and ``/safety``; these aliases expose the
same functionality under the suggested paths without duplicating logic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.container import AppContainer
from app.dependencies import get_container
from app.schemas.actions import ActionProposal
from app.schemas.api import ProposalRequest

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


@router.post("/propose")
async def propose(
    request: ProposalRequest,
    container: AppContainer = Depends(get_container),
) -> dict:
    """Alias of ``POST /api/v1/actions/propose``."""
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


@router.get("")
def list_decisions(
    limit: int = Query(50, ge=1, le=500),
    container: AppContainer = Depends(get_container),
) -> dict:
    items = container.decision_repo.list(limit=limit)
    return {"items": [d.model_dump(mode="json") for d in items], "total": len(items)}


@router.get("/{decision_id}")
def get_decision(
    decision_id: str, container: AppContainer = Depends(get_container)
) -> dict:
    decision = container.decision_repo.get(decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision.model_dump(mode="json")
