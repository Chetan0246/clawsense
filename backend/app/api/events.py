"""Event history endpoints (search, filter, paginate, export)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.container import AppContainer
from app.dependencies import get_container

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("")
def list_events(
    category: str | None = Query(None),
    severity: str | None = Query(None),
    event_type: str | None = Query(None),
    device_id: str | None = Query(None),
    proposal_id: str | None = Query(None),
    command_id: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    container: AppContainer = Depends(get_container),
) -> dict:
    items, total = container.event_repo.query(
        category=category,
        severity=severity,
        event_type=event_type,
        device_id=device_id,
        proposal_id=proposal_id,
        command_id=command_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [e.model_dump(mode="json") for e in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
def stats(container: AppContainer = Depends(get_container)) -> dict:
    return {"by_category": container.event_repo.count_by_category()}


@router.get("/export.csv")
def export_csv(
    category: str | None = Query(None),
    severity: str | None = Query(None),
    container: AppContainer = Depends(get_container),
) -> PlainTextResponse:
    csv_text = container.event_repo.export_csv(category=category, severity=severity)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=clawsense-events.csv"},
    )


@router.get("/{event_id}")
def get_event(event_id: str, container: AppContainer = Depends(get_container)) -> dict:
    event = container.event_repo.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event.model_dump(mode="json")
