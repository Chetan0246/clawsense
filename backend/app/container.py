"""Application container: constructs and owns all long-lived components.

Centralising construction keeps ``main.py`` small and makes the whole system
easy to build in tests with isolated settings (e.g. an in-memory database).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings
from app.db.database import Database
from app.repositories.command_repository import CommandRepository
from app.repositories.decision_repository import DecisionRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.event_repository import EventRepository
from app.repositories.proposal_repository import ProposalRepository
from app.repositories.telemetry_repository import TelemetryRepository
from app.repositories.transition_repository import TransitionRepository
from app.services.agent_adapter import AgentAdapter, create_agent
from app.services.event_bus import EventBus
from app.services.state_machine import SystemStateMachine
from app.services.supervisor import Supervisor
from app.simulation.device import SimulatedEsp32
from app.simulation.loop import ControlLoop
from app.transports.base import DeviceTransport
from app.transports.http_transport import HttpDeviceTransport
from app.transports.simulated import SimulatedDeviceTransport


@dataclass
class AppContainer:
    settings: Settings
    db: Database
    bus: EventBus
    state_machine: SystemStateMachine
    supervisor: Supervisor
    loop: ControlLoop
    device: SimulatedEsp32 | None = None
    transport: DeviceTransport | None = None
    agent: AgentAdapter | None = None

    # repositories (also reachable via supervisor, kept here for API access)
    telemetry_repo: TelemetryRepository | None = None
    proposal_repo: ProposalRepository | None = None
    decision_repo: DecisionRepository | None = None
    command_repo: CommandRepository | None = None
    event_repo: EventRepository | None = None
    transition_repo: TransitionRepository | None = None
    device_repo: DeviceRepository | None = None

    async def shutdown(self) -> None:
        await self.loop.stop()
        self.db.close()


def build_container(settings: Settings) -> AppContainer:
    db = Database(settings.db_path)
    db.initialize()

    bus = EventBus()

    telemetry_repo = TelemetryRepository(db)
    proposal_repo = ProposalRepository(db)
    decision_repo = DecisionRepository(db)
    command_repo = CommandRepository(db)
    event_repo = EventRepository(db)
    transition_repo = TransitionRepository(db)
    device_repo = DeviceRepository(db)

    state_machine = SystemStateMachine(settings=settings)

    device: SimulatedEsp32 | None = None
    transport: DeviceTransport
    if settings.device_transport == "http":
        transport = HttpDeviceTransport(settings)
    else:
        device = SimulatedEsp32(device_id=settings.device_id)
        transport = SimulatedDeviceTransport(device)

    agent = create_agent(settings, device=device)

    supervisor = Supervisor(
        settings,
        transport=transport,
        state_machine=state_machine,
        agent=agent,
        device=device,
        bus=bus,
        telemetry_repository=telemetry_repo,
        proposal_repository=proposal_repo,
        decision_repository=decision_repo,
        command_repository=command_repo,
        event_repository=event_repo,
        transition_repository=transition_repo,
    )

    loop = ControlLoop(supervisor, settings)

    device_repo.upsert(
        settings.device_id,
        device_type="esp32s3",
        firmware_version=device.firmware_version if device else None,
        connectivity_status="connected" if device else "unknown",
        simulated=settings.is_simulation,
    )

    return AppContainer(
        settings=settings,
        db=db,
        bus=bus,
        state_machine=state_machine,
        supervisor=supervisor,
        loop=loop,
        device=device,
        transport=transport,
        agent=agent,
        telemetry_repo=telemetry_repo,
        proposal_repo=proposal_repo,
        decision_repo=decision_repo,
        command_repo=command_repo,
        event_repo=event_repo,
        transition_repo=transition_repo,
        device_repo=device_repo,
    )
