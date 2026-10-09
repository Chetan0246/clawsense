# ClawSense

**A context-aware agentic IoT system with deterministic safety validation and offline fallback on ESP32-S3.**

ClawSense demonstrates a supervisory control architecture in which an AI agent may
*propose* actions, but an independent, deterministic **safety supervisor** decides
whether they may run — and a local rule-based controller takes over when the AI
service or network is unavailable.

> **The engineering contribution is the supervisory control and safety
> architecture — not the LLM, not the dashboard, and not the ESPClaw demo.**

---

## Share this project

Copy-paste summary for sharing:

> **ClawSense** — an ESP32-S3 IoT system where an LLM agent proposes actuator
> actions, but a deterministic **safety supervisor** (independent of the LLM)
> validates every proposal, with an explicit state machine and an **offline
> fallback controller** when the agent is unreachable. Includes a FastAPI/SQLite
> backend, a React dashboard, firmware, and a 78-test pytest suite.
> <https://github.com/Chetan0246/clawsense>

---

## ⚠️ Safety notice

- In the default **simulation** mode every sensor value and actuator result is
  **simulated**. It is clearly labelled `SIMULATED` in the API and with a banner in
  the dashboard. Simulated data must never be presented as real hardware data.
- A software "approved" decision is **not** proof of physical safety. The ESP32
  firmware independently re-validates every command before touching an actuator.
- Do **not** connect a real actuator (servo, buzzer, mains load) without
  independent hardware protection, a correctly rated separate power supply, and a
  common ground. See [`docs/wiring.md`](docs/wiring.md).
- This is a research/demonstration prototype, **not** a certified functional-safety
  system.

---

## Problem statement and objectives

**Problem.** Agentic/AI control of physical devices is attractive but unsafe by
default: an LLM can hallucinate an action, invent a parameter, or act on stale
context. Naively wiring model output to an actuator removes every guarantee a
control system normally relies on.

**Objectives.**

1. Show that an AI agent can drive an IoT device *safely*, by placing a
   deterministic, independently testable supervisor between the agent and the
   hardware.
2. Show that the system keeps operating safely when the AI service or the network
   disappears, using a local rule-based controller.
3. Make every stage — proposal, validation, dispatch, acknowledgement — explicit,
   observable, and auditable.
4. Keep the AI strictly optional: the system must work with no API key at all.

**Main contribution.** The ClawSense supervisory control and safety architecture:
an eight-check deterministic safety supervisor with no LLM dependency, an explicit
failure/recovery state machine, a documented offline fallback, a command lifecycle
that never confuses approval with physical execution, and an on-device second
validator.

---

## Hardware

| Component | Notes |
| --- | --- |
| ESP32-S3-DevKitC-1 | MCU, Wi-Fi, Arduino/PlatformIO |
| DHT22 | temperature + humidity (digital) |
| PIR motion sensor | digital |
| Third sensor (configurable) | **reports `NOT_CONFIGURED` until configured — never fabricated** |
| SSD1306 OLED 128×64 (I²C, 0x3C) | local status display |
| Hobby servo | **separate 5 V supply + common ground** |
| Piezo buzzer | bounded alert |
| Green / yellow / red LEDs | status semantics (see `docs/wiring.md`) |
| Push buttons | local, non-actuator actions only |
| Breadboard, jumpers, 5 V supply | — |

Wiring, voltage requirements, and the safe state are in [`docs/wiring.md`](docs/wiring.md).
Pin assignments are centralized in [`firmware/include/config.h`](firmware/include/config.h).

## Software prerequisites

| Tool | Version used | Purpose |
| --- | --- | --- |
| Python | 3.11+ (verified on 3.14) | backend |
| Node.js | 18+ (verified on 22) | dashboard |
| npm | 9+ (verified on 10) | dashboard deps |
| PlatformIO (VS Code or CLI) | latest | firmware build/flash (optional) |

## Simulation versus hardware mode

| | `simulation` (default) | `hardware` |
| --- | --- | --- |
| Telemetry source | deterministic simulated device | ESP32-S3 over HTTP |
| Agent | deterministic simulated agent | ESPClaw/LLM adapter (if configured) |
| Device transport | in-process | `HttpDeviceTransport` |
| Labelled | `SIMULATION MODE` banner + `simulated: true` everywhere | `simulated: false` |
| Needs API key | no | only if the real agent is enabled |

Switch with `CLAWSENSE_APP_MODE=hardware` and `CLAWSENSE_DEVICE_TRANSPORT=http`.
The dashboard always distinguishes simulated from real data; a simulated result
is never presented as a hardware result.

## Firmware flashing

See [`firmware/README.md`](firmware/README.md) for the full procedure.

```bash
cd firmware
cp include/secrets.example.h include/secrets.h   # fill in Wi-Fi (git-ignored)
pio run -t upload
pio device monitor                                # 115200 baud
```

**Test the ESP32 without the servo connected first** (plan section 3, hardware
rule 7). If the servo causes resets or Wi-Fi drops, disconnect it and use the
LEDs and buzzer as the actuator demonstration.

---

## What the system demonstrates

1. Sensor data acquisition from an ESP32-S3 (temperature, humidity, motion, light).
2. Event generation with change/edge detection and short-term contextual memory.
3. AI action proposals through a pluggable agent adapter (simulated or ESPClaw/LLM).
4. **Deterministic action validation independent of the LLM.**
5. Safe actuator command execution with full lifecycle tracking.
6. Local rule-based fallback when the AI service or network is unavailable.
7. Explicit system state transitions, recovery, and an append-only audit log.
8. A professional, responsive web dashboard.

---

## Architecture

```
        ┌──────────────────────────────────────────────────────────────┐
        │                      ClawSense backend                        │
        │                                                                │
 sensors│  ┌────────────┐   ┌───────────────┐   ┌───────────────────┐   │
 ───────┼─▶│ Event      │──▶│ Context       │──▶│ Agent adapter      │   │
        │  │ engine     │   │ memory        │   │ (simulated/ESPClaw)│   │
        │  └────────────┘   └───────────────┘   └─────────┬─────────┘   │
        │                                                  │ proposal    │
        │                                                  ▼             │
        │   ┌──────────────────────┐            ┌────────────────────┐  │
        │   │ Local fallback       │            │ DETERMINISTIC       │  │
        │   │ controller (no LLM)  │───────────▶│ SAFETY SUPERVISOR   │  │
        │   └──────────────────────┘  proposal  │ schema·allow-list   │  │
        │             ▲                          │ range·context·state │  │
        │             │                          │ cooldown·duplicate  │  │
        │   ┌─────────┴──────────┐               └─────────┬──────────┘  │
        │   │ State machine      │                         │ approved    │
        │   │ ONLINE·DEGRADED·   │◀────────────────────────┘             │
        │   │ OFFLINE·RECOVERY·  │                                       │
        │   │ SAFE_LOCKDOWN      │        ┌───────────────────────┐      │
        │   └────────────────────┘        │ Command dispatcher    │      │
        │                                 │ (lifecycle + timeout) │      │
        │                                 └───────────┬───────────┘      │
        └─────────────────────────────────────────────┼──────────────────┘
                                                       │ command
                                                       ▼
                                          ┌──────────────────────────┐
                                          │  Device transport         │
                                          │  simulated | HTTP (ESP32) │
                                          └────────────┬─────────────┘
                                                       ▼
                              ┌────────────────────────────────────────────┐
                              │ ESP32-S3 firmware                           │
                              │ sensors → events → context → on-device      │
                              │ safety supervisor → actuator manager        │
                              │ + local fallback controller                 │
                              └────────────────────────────────────────────┘
```

Key rule: **the LLM is never on the execution path.** Its output is only ever a
proposal that must pass the supervisor.

---

## Repository layout

```
clawsense/
├── PLAN.md                  # the full specification
├── README.md                # this file
├── .env.example             # configuration placeholders (copy to .env)
├── backend/                 # FastAPI supervisory backend + tests
│   ├── app/
│   │   ├── api/             # versioned REST + WebSocket endpoints
│   │   ├── db/              # SQLite schema + connection
│   │   ├── repositories/    # small persistence abstraction
│   │   ├── schemas/         # pydantic contracts
│   │   ├── services/        # safety supervisor, state machine, fallback, …
│   │   ├── simulation/      # deterministic simulated device + control loop
│   │   ├── transports/      # simulated + HTTP device transports
│   │   ├── config.py        # env-driven, typed settings
│   │   ├── container.py     # dependency wiring
│   │   └── main.py          # FastAPI app
│   └── tests/               # 78 tests
├── frontend/                # React + Vite + TypeScript + Tailwind dashboard
│   └── src/{pages,components,hooks,api}
├── firmware/                # ESP32-S3 Arduino/PlatformIO firmware
├── docs/                    # architecture, wiring, safety model, API, testing, demo
└── scripts/                 # dev + demo helpers
```

---

## Quickstart

### 1. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp ../.env.example .env          # optional: adjust settings (never commit .env)
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/v1/health>
- WebSocket: `ws://localhost:8000/ws`

### 2. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api and /ws to the backend)
```

### 3. Run the guided demo

```bash
./scripts/demo.sh          # against http://localhost:8000
```

Or simply open the dashboard and use **System Health → Simulation Controls**.

---

## Configuration

All backend settings use the `CLAWSENSE_` prefix and are documented in
[`.env.example`](.env.example). The most important:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLAWSENSE_APP_MODE` | `simulation` | `simulation` or `hardware` |
| `CLAWSENSE_AGENT_PROVIDER` | `simulated` | `simulated` or `espclaw` |
| `CLAWSENSE_ESPCLAW_ENDPOINT` | _(empty)_ | ESPClaw/LLM endpoint; empty disables it |
| `CLAWSENSE_LLM_API_KEY` | _(empty)_ | **Backend-only secret — never sent to the browser** |
| `CLAWSENSE_DEVICE_TRANSPORT` | `simulated` | `simulated` or `http` |
| `CLAWSENSE_DEVICE_BASE_URL` | `http://192.168.0.50` | ESP32 base URL in hardware mode |
| `CLAWSENSE_DEGRADED_TIMEOUT_SECONDS` | `15` | Agent silence before `DEGRADED` |
| `CLAWSENSE_OFFLINE_TIMEOUT_SECONDS` | `45` | Agent silence before `OFFLINE_LOCAL` |
| `CLAWSENSE_SERVO_MIN/MAX_DEGREES` | `0` / `180` | Deterministic servo limits |
| `CLAWSENSE_ACTION_COOLDOWN_SECONDS` | `3` | Minimum repeat interval per action |

**Secrets:** no secret is ever hard-coded. `.env` is git-ignored; `.env.example`
contains placeholders only. The LLM key is used server-side only and never
appears in API responses or the frontend bundle.

---

## The deterministic safety checks

Every proposal is evaluated against eight independently reported checks:

| # | Check | Rejects when |
| --- | --- | --- |
| 1 | `schema` | payload is not an object / required fields missing or wrong type |
| 2 | `allow_list` | action is not one of `servo_move`, `buzzer_beep`, `set_status_led`, `no_op` |
| 3 | `parameter_types` | parameters don't match the action's schema (missing, wrong type, unknown keys) |
| 4 | `range` | servo angle outside `0–180`, buzzer duration outside `1–2000 ms` |
| 5 | `context_freshness` | no sensor context, or older than `context_max_age_seconds` |
| 6 | `system_state` | source not permitted in the current state (e.g. agent commands in `OFFLINE_LOCAL`, anything in `SAFE_LOCKDOWN`) |
| 7 | `cooldown` | same action repeated within `action_cooldown_seconds` |
| 8 | `duplicate` | identical action+parameters already issued within the window |

The decision includes a machine-readable `reason_code`, a human explanation, and
the full per-check detail. See [`docs/safety-model.md`](docs/safety-model.md).

---

## State machine

```
ONLINE_AGENT ──▶ DEGRADED ──▶ OFFLINE_LOCAL ──▶ RECOVERY ──▶ ONLINE_AGENT
      │              │              │                │
      └──────────────┴──────────────┴────────────────┴────▶ SAFE_LOCKDOWN
                                                              │
                                          (operator reset) ───┘──▶ RECOVERY
```

Illegal transitions are refused. `SAFE_LOCKDOWN` has no automatic exit.

---

## Testing

```bash
cd backend && .venv/bin/python -m pytest        # 78 passed
cd frontend && npm run build                    # typecheck + production build
```

See [`docs/testing.md`](docs/testing.md) for the full test matrix.

---

## Firmware

See [`firmware/README.md`](firmware/README.md) and [`docs/wiring.md`](docs/wiring.md).

```bash
cd firmware
pio run -t upload      # requires PlatformIO + an ESP32-S3
pio device monitor
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Dashboard shows "Backend error" / no data | backend not running or wrong port | start the backend; the dev proxy targets `localhost:8000` |
| WebSocket shows `down` | backend stopped or proxy misconfigured | check `ws://localhost:8000/ws`; ensure you use `npm run dev`, not a static file server |
| `POST /actions/propose` returns `CONTEXT_MISSING` | no telemetry yet (fresh start) | wait one control cycle, or `POST /telemetry/ingest` |
| Proposal rejected with `COOLDOWN_ACTIVE` | same action within `action_cooldown_seconds` | wait for the window, or change the parameters |
| Proposal rejected with `INVALID_SYSTEM_STATE` | system is `OFFLINE_LOCAL`/`RECOVERY` (agent commands blocked) or `SAFE_LOCKDOWN` | restore the agent, or `POST /system/reset` |
| System stuck in `OFFLINE_LOCAL` | agent forced offline | `POST /simulation/agent/availability {"available": true}` |
| Commands stay `FAILED`/`TIMEOUT` | failure injection left on | `POST /simulation/failure {"mode": "none"}` |
| State never degrades when testing offline | timeouts too long for a demo | set `CLAWSENSE_DEGRADED_TIMEOUT_SECONDS=2`, `CLAWSENSE_OFFLINE_TIMEOUT_SECONDS=4` |
| `npm run build` fails on types | stale `node_modules` | `rm -rf node_modules && npm install` |
| Port already in use | another process on 8000/5173 | set `CLAWSENSE_PORT` / `FRONTEND_PORT` |
| Firmware resets when the servo moves | servo powered from the board | use a separate 5 V supply with a common ground and a bulk capacitor |

## Self-assessment

An honest assessment against the plan's review rubric, including the Definition
of Done checklist and the list of requirements that could **not** be fully
satisfied in this environment, is in
[`docs/self-assessment.md`](docs/self-assessment.md).

---

## Limitations

This is a prototype. It is **not** certified for safety-critical use; it has no
hardware watchdog for the actuator power path, no formal verification, no
authentication/authorisation layer, and the ESPClaw integration is an adapter
that requires a verified endpoint. See
[`docs/limitations.md`](docs/limitations.md) for the complete list.
