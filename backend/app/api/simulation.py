"""Simulation / demo control endpoints.

These endpoints let an operator drive the demonstration: change the simulated
scenario, force the agent offline, or inject a device failure.  They are
clearly namespaced under ``/simulation`` and are only meaningful in simulation
mode.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.container import AppContainer
from app.dependencies import get_container
from app.schemas.api import (
    AgentAvailabilityRequest,
    AgentModeRequest,
    FailureRequest,
    ScenarioRequest,
)
from app.services.agent_adapter import SimulatedAgent

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"])


@router.get("/state")
def state(container: AppContainer = Depends(get_container)) -> dict:
    device_state = container.device.state_dict() if container.device else None
    return {
        "mode": container.settings.app_mode,
        "simulated": container.settings.is_simulation,
        "device": device_state,
        "agent_provider": container.settings.agent_provider,
        "agent_mode": (
            container.agent.mode.value
            if isinstance(container.agent, SimulatedAgent)
            else None
        ),
        "transport_failure_mode": (
            container.transport.failure_mode.value
            if getattr(container.transport, "failure_mode", None) is not None
            else None
        ),
    }


@router.post("/scenario")
def set_scenario(
    request: ScenarioRequest,
    container: AppContainer = Depends(get_container),
) -> dict:
    if container.device is None:
        raise HTTPException(
            status_code=409, detail="Scenario control requires simulation mode."
        )
    container.supervisor.set_scenario(request.scenario)
    return {"scenario": request.scenario.value}


@router.post("/agent")
def set_agent_mode(
    request: AgentModeRequest,
    container: AppContainer = Depends(get_container),
) -> dict:
    if not isinstance(container.agent, SimulatedAgent):
        raise HTTPException(
            status_code=409, detail="Agent mode control requires the simulated agent."
        )
    try:
        container.agent.mode = SimulatedAgent.Mode(request.mode)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown agent mode: {request.mode}")
    return {"agent_mode": container.agent.mode.value}


@router.post("/agent/availability")
def set_agent_availability(
    request: AgentAvailabilityRequest,
    container: AppContainer = Depends(get_container),
) -> dict:
    container.supervisor.set_agent_available(request.available)
    return {"agent_available": request.available}


@router.post("/failure")
def set_failure_mode(
    request: FailureRequest,
    container: AppContainer = Depends(get_container),
) -> dict:
    container.supervisor.set_failure_mode(request.mode)
    return {"failure_mode": request.mode.value}
