"""WebSocket transport (PLAN.md section 18).

Pushes typed messages to connected dashboards.  Every message has the shape::

    {"type": "<type>", "data": <payload>, "seq": <int>}

Message types: ``telemetry``, ``event``, ``decision``, ``command``,
``system``, ``snapshot``, ``pong``.  A client can send ``{"type":"ping"}``
to keep the connection alive.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.container import AppContainer

router = APIRouter(tags=["websocket"])


def _initial_snapshot(container: AppContainer) -> dict:
    supervisor = container.supervisor
    decision = supervisor.latest_decision or container.decision_repo.latest()
    command = supervisor.latest_command or container.command_repo.latest()
    events, _ = container.event_repo.query(limit=30)
    return {
        "system": supervisor.status_payload(),
        "telemetry": (
            supervisor.latest_telemetry.model_dump(mode="json")
            if supervisor.latest_telemetry
            else None
        ),
        "decision": decision.model_dump(mode="json") if decision else None,
        "command": command.model_dump(mode="json") if command else None,
        "events": [e.model_dump(mode="json") for e in events],
        "simulated": container.settings.is_simulation,
        "mode": container.settings.app_mode,
    }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    container: AppContainer = websocket.app.state.container
    queue = container.bus.subscribe()
    seq = 0
    try:
        await websocket.send_json(
            {"type": "snapshot", "data": _initial_snapshot(container), "seq": seq}
        )

        async def _forward() -> None:
            nonlocal seq
            while True:
                message = await queue.get()
                seq += 1
                message = {**message, "seq": seq}
                await websocket.send_json(message)

        forward_task = asyncio.create_task(_forward())
        try:
            while True:
                client_message = await websocket.receive_json()
                if isinstance(client_message, dict) and client_message.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "data": {}, "seq": seq})
        finally:
            forward_task.cancel()
            try:
                await forward_task
            except asyncio.CancelledError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        # Never let a single client's error affect the control loop.
        pass
    finally:
        container.bus.unsubscribe(queue)
