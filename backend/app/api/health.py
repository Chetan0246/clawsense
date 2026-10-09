"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.container import AppContainer
from app.dependencies import get_container

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health(container: AppContainer = Depends(get_container)) -> dict:
    status = container.state_machine.status()
    return {
        "status": "ok",
        "version": __version__,
        "mode": container.settings.app_mode,
        "simulated": container.settings.is_simulation,
        "current_state": status.current_state.value,
        "uptime_seconds": round(status.uptime_seconds, 3),
        "websocket_subscribers": container.bus.subscriber_count,
        "control_cycles": container.loop.cycles,
        "control_errors": container.loop.errors,
    }


@router.get("/ready")
def ready(container: AppContainer = Depends(get_container)) -> dict:
    """Readiness: the database is initialised and the container is built."""
    container.db.query_one("SELECT 1 AS ok")
    return {"ready": True}
