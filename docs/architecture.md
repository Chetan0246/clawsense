# Architecture

This document describes the ClawSense supervisory control architecture, the
responsibility of each component, the data flow, and the rationale for the main
design decisions.

## Design principle

> The AI proposes. The deterministic supervisor decides. The device re-validates.

Nothing the agent produces is trusted. The agent never touches GPIO, never
validates its own output, and never executes anything. The only path to an
actuator is:

```
proposal → deterministic safety supervisor → command dispatcher → transport → device re-validation
```

## Components

### Backend (`backend/app/`)

| Component | File | Responsibility |
| --- | --- | --- |
| **Event engine** | `services/event_engine.py` | Turns telemetry into typed events using change detection, threshold crossing, and motion edge detection. Debounced to avoid noise. |
| **Context memory** | `services/context_memory.py` | Bounded rolling buffer of recent events, latest readings, and recently executed actions. Produces a concise summary for the agent. Backend mirror of the device's bounded buffer. |
| **Agent adapter** | `services/agent_adapter.py` | Pluggable proposal source. `SimulatedAgent` (deterministic, offline) and `EspClawAgent` (HTTP adapter). Malformed agent responses are discarded, never guessed at. |
| **Safety supervisor** | `services/safety_supervisor.py` | **Core contribution.** Eight independent, deterministic checks. No LLM dependency. Fails closed. |
| **State machine** | `services/state_machine.py` | Explicit states and validated transitions, driven by health signals and timeouts. |
| **Fallback controller** | `services/fallback_controller.py` | Deterministic local rules that run without the network or LLM. |
| **Command dispatcher** | `services/command_dispatcher.py` | Owns the command lifecycle and the distinction between "approved" and "physically executed". Handles timeouts and communication uncertainty. |
| **Audit log** | `services/audit.py` | Single entry point that persists every event, updates context, and broadcasts to dashboards. |
| **Supervisor / orchestrator** | `services/supervisor.py` | Composes one control cycle: telemetry → context/events → state evaluation → controller selection → proposal → validation → dispatch. |
| **Event bus** | `services/event_bus.py` | Bounded per-subscriber queues for WebSocket fan-out. Slow clients cannot block the control loop. |

### AI integration: ESPClaw and the agent adapter

The plan requires using "the existing, verified ESPClaw integration". No ESPClaw
installation was present in this repository, and PLAN.md is explicit that ESPClaw
APIs must not be invented. The integration point is therefore made **explicit and
swappable** rather than guessed at:

- `AgentAdapter` (`services/agent_adapter.py`) is the interface every agent
  provider implements: `available` and `async propose(context)`.
- `EspClawAgent` is the real adapter. It documents the expected contract
  (`POST {CLAWSENSE_ESPCLAW_ENDPOINT}/propose` with a bounded context summary,
  returning `{action, parameters, reason}`), attaches the LLM API key
  **server-side only**, and fails closed: an unset endpoint raises
  `AgentUnavailable`, a timeout raises `AgentTimeout`, and any response that does
  not validate against the action contract is **discarded** rather than guessed at.
- `SimulatedAgent` is the deterministic offline stand-in used for demos and tests.

Responsibilities in the pipeline:

| Layer | Responsibility | Explicitly NOT responsible for |
| --- | --- | --- |
| ESPClaw / LLM | propose a structured action from context | validation, GPIO, execution |
| Agent adapter | transport, timeout, discard malformed output | safety policy |
| Backend supervisor | deterministic validation, persistence, dispatch | physical safety |
| Firmware | independent re-validation, actuation | trusting the backend |
| Dashboard | observe and request (validated) proposals | direct GPIO, bypassing validation |

Because the ESPClaw endpoint has not been verified against a live instance, the
project runs entirely on `SimulatedAgent` by default and the limitation is
recorded in [`limitations.md`](limitations.md).

### Transports (`backend/app/transports/`)

- `SimulatedDeviceTransport` — deterministic in-process device; supports injected
  failure modes (`none`, `timeout`, `reject`, `uncertain`).
- `HttpDeviceTransport` — talks to a real ESP32-S3 over `GET /health`,
  `GET /telemetry`, `POST /command`, with bounded retries and timeouts.

### Persistence (`backend/app/db`, `repositories/`)

A small repository abstraction over stdlib `sqlite3` (explicitly permitted by the
plan). Tables: `devices`, `telemetry`, `proposals`, `safety_decisions`,
`commands`, `events`, `state_transitions`. Safety decisions and command results
are stored independently so a restart does not erase history.

### Simulation (`backend/app/simulation/`)

- `SimulatedEsp32` — deterministic model of the sensor/actuator node with
  scenarios: `normal`, `heatwave`, `cold`, `motion`, `high_humidity`,
  `sensor_fault`, `stale`.
- `ControlLoop` — fixed-cadence, defensive background task that drives the
  supervisor's control cycle.

### Firmware (`firmware/`)

Mirrors the backend architecture on the device: sensor manager, event engine,
bounded context buffer, **on-device deterministic safety supervisor**, local
fallback controller, state machine, actuator manager, non-blocking communication,
and OLED display. See [`wiring.md`](wiring.md).

## Data flow

1. **Acquire** — the control loop obtains a telemetry snapshot from the transport.
2. **Ingest** — readings are persisted; the event engine emits typed events; the
   context buffer is updated; telemetry is broadcast to dashboards.
3. **Evaluate state** — the state machine checks agent/network health and applies
   any warranted transition (with an explicit reason code).
4. **Select controller**
   - `ONLINE_AGENT` / `DEGRADED` → ask the agent for a proposal.
   - `OFFLINE_LOCAL` / `RECOVERY` → run the deterministic fallback rules.
   - `SAFE_LOCKDOWN` → stop; no actuator commands are permitted.
5. **Validate** — the safety supervisor evaluates all eight checks and records a
   decision.
6. **Dispatch** — if approved, the dispatcher sends the command and tracks
   `DISPATCHED → ACKNOWLEDGED → STATE_CONFIRMED`, or `TIMEOUT` / `FAILED` /
   `UNCERTAIN` on failure.
7. **Audit** — every stage emits an event correlated by `proposal_id` /
   `command_id`.

## Design decisions and trade-offs

- **Deterministic checks, not ML, for safety.** The supervisor is ordinary,
  auditable code. Given identical inputs and configuration it always produces the
  identical decision. This is what makes the safety claim testable.
- **Fail closed.** Unknown actions, malformed payloads, missing or stale context,
  and illegal states all produce rejection — never a "best guess".
- **Two independent validators.** The backend supervisor and the on-device
  supervisor are separate implementations with the same limits. A backend bug
  cannot by itself drive an actuator out of range.
- **SQLite behind a repository, not an ORM.** Zero compiled dependencies, fully
  deterministic behaviour, and a persistence boundary that keeps the domain code
  storage-agnostic.
- **Explicit `simulated` flag everywhere.** Simulated data can never be silently
  presented as real hardware data.
- **Explicit state machine.** Recovery is a first-class, observable process, not
  an implicit retry.

## Related documents

- [`safety-model.md`](safety-model.md) — the checks and the safety argument
- [`api-reference.md`](api-reference.md) — REST and WebSocket contracts
- [`testing.md`](testing.md) — how the behaviour is verified
- [`limitations.md`](limitations.md) — what this prototype does *not* do
