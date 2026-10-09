"""Telemetry endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.container import AppContainer
from app.dependencies import get_container
from app.schemas.api import TelemetryIngestRequest
from app.schemas.telemetry import SensorReading, TelemetrySnapshot

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


@router.post("/ingest")
async def ingest(
    request: TelemetryIngestRequest,
    container: AppContainer = Depends(get_container),
) -> dict:
    """Accept a telemetry push from a device.

    Runs the full ingestion path (persistence, event generation, context update,
    WebSocket broadcast) exactly like the polling transport.
    """
    now = request.timestamp or datetime.now(timezone.utc)
    readings: dict[str, SensorReading] = {}
    for name, payload in request.readings.items():
        readings[name] = SensorReading(
            sensor=name,
            value=payload.value,
            unit=payload.unit,
            status=payload.status,
            timestamp=payload.timestamp or now,
            simulated=request.simulated,
            detail=payload.detail,
        )
    snapshot = TelemetrySnapshot(
        device_id=request.device_id,
        timestamp=now,
        simulated=request.simulated,
        readings=readings,
    )
    events = await container.supervisor.ingest_telemetry(snapshot)
    return {
        "accepted": True,
        "device_id": request.device_id,
        "readings": len(readings),
        "events_generated": len(events),
    }


@router.get("/latest")
def latest(container: AppContainer = Depends(get_container)) -> dict:
    snapshot = container.supervisor.latest_telemetry
    if snapshot is None:
        # Fall back to the most recent persisted readings.
        readings = container.telemetry_repo.latest(container.settings.device_id)
        return {
            "device_id": container.settings.device_id,
            "timestamp": None,
            "simulated": container.settings.is_simulation,
            "readings": {
                r.sensor: r.model_dump(mode="json") for r in readings
            },
            "available": False,
        }
    payload = snapshot.model_dump(mode="json")
    payload["available"] = True
    payload["age_seconds"] = container.supervisor.context.telemetry_age_seconds()
    return payload


@router.get("/history")
def history(
    sensor: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    container: AppContainer = Depends(get_container),
) -> dict:
    items = container.telemetry_repo.history(sensor=sensor, limit=limit)
    return {"items": items, "total": len(items), "sensor": sensor}
