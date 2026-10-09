"""ClawSense FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import (
    actions,
    decisions,
    events,
    health,
    safety,
    simulation,
    system,
    telemetry,
    ws,
)
from app.config import Settings, get_settings
from app.container import build_container

logger = logging.getLogger("clawsense")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = build_container(settings)
        app.state.container = container
        if settings.simulator_enabled:
            container.loop.start()
            logger.info(
                "ClawSense started in %s mode (simulated=%s)",
                settings.app_mode,
                settings.is_simulation,
            )
        try:
            yield
        finally:
            await container.shutdown()

    app = FastAPI(
        title="ClawSense",
        description=(
            "Context-aware agentic IoT supervisory control with deterministic "
            "safety validation and offline fallback."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # The dashboard is a separate origin during development.  Only localhost
    # origins are permitted; no credentials are exposed cross-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(system.router)
    app.include_router(telemetry.router)
    app.include_router(events.router)
    app.include_router(safety.router)
    app.include_router(actions.router)
    app.include_router(decisions.router)
    app.include_router(simulation.router)
    app.include_router(ws.router)

    @app.get("/", include_in_schema=False)
    def root() -> JSONResponse:
        return JSONResponse(
            {
                "name": "ClawSense",
                "version": __version__,
                "docs": "/docs",
                "api": "/api/v1/health",
                "websocket": "/ws",
            }
        )

    return app


app = create_app()


def run() -> None:  # pragma: no cover - manual entrypoint
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
