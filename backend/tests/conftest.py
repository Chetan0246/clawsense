"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import AppContainer, build_container
from app.main import create_app
from app.schemas.actions import ActionProposal
from app.schemas.telemetry import SensorReading, SensorStatus, TelemetrySnapshot
from app.services.context_memory import ContextMemory


def make_settings(**overrides) -> Settings:
    defaults = dict(
        db_path=":memory:",
        app_mode="simulation",
        device_transport="simulated",
        agent_provider="simulated",
        simulator_enabled=False,
        simulator_interval_seconds=0.02,
        action_cooldown_seconds=3.0,
        context_max_age_seconds=30.0,
        degraded_timeout_seconds=10.0,
        offline_timeout_seconds=20.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def container(settings: Settings) -> AppContainer:
    c = build_container(settings)
    yield c
    c.db.close()


def fresh_context(
    *,
    now: datetime | None = None,
    temperature: float = 24.0,
    humidity: float = 50.0,
    motion: bool = False,
    age_seconds: float = 0.0,
) -> ContextMemory:
    """Build a context with a telemetry snapshot of a given age."""
    now = now or datetime.now(timezone.utc)
    ts = now - timedelta(seconds=age_seconds)
    snapshot = TelemetrySnapshot(
        device_id="esp32s3-clawsense-01",
        timestamp=ts,
        simulated=True,
        readings={
            "temperature_c": SensorReading(
                sensor="temperature_c",
                value=temperature,
                unit="C",
                status=SensorStatus.OK,
                timestamp=ts,
                simulated=True,
            ),
            "humidity_percent": SensorReading(
                sensor="humidity_percent",
                value=humidity,
                unit="%",
                status=SensorStatus.OK,
                timestamp=ts,
                simulated=True,
            ),
            "motion": SensorReading(
                sensor="motion",
                value=motion,
                unit="bool",
                status=SensorStatus.OK,
                timestamp=ts,
                simulated=True,
            ),
        },
    )
    ctx = ContextMemory()
    ctx.update_telemetry(snapshot)
    return ctx


@pytest.fixture
def servo_proposal():
    def _make(angle: int = 90, source: str = "agent") -> ActionProposal:
        return ActionProposal(
            action="servo_move",
            parameters={"angle_degrees": angle},
            reason="test",
            source=source,
        )

    return _make


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def live_client() -> TestClient:
    """A client with the background control loop running.

    The agent is forced into no-op mode so API tests are deterministic and the
    background loop does not race the test's own proposals.
    """
    settings = make_settings(simulator_enabled=True, simulator_interval_seconds=0.02)
    app = create_app(settings)
    with TestClient(app) as test_client:
        test_client.post("/api/v1/simulation/agent", json={"mode": "noop"})
        yield test_client
