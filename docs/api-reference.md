# API reference

Base URL: `http://localhost:8000`. Interactive docs: `/docs` (OpenAPI).
All endpoints are versioned under `/api/v1` except the WebSocket.

The backend never returns secrets. The LLM API key is server-side only.

---

## Health

### `GET /api/v1/health`
```json
{
  "status": "ok",
  "version": "0.1.0",
  "mode": "simulation",
  "simulated": true,
  "current_state": "ONLINE_AGENT",
  "uptime_seconds": 12.4,
  "websocket_subscribers": 1,
  "control_cycles": 6,
  "control_errors": 0
}
```

### `GET /api/v1/ready`
```json
{ "ready": true }
```

---

## System

### `GET /api/v1/system/status`
```json
{
  "current_state": "ONLINE_AGENT",
  "previous_state": null,
  "transition_reason_code": null,
  "transition_reason": null,
  "last_transition_at": null,
  "controller_authority": "agent",
  "agent_available": true,
  "agent_provider": "simulated",
  "network_available": true,
  "device_connected": true,
  "last_successful_agent_request": "2026-01-01T12:00:00Z",
  "last_successful_device_communication": "2026-01-01T12:00:02Z",
  "recovery_status": "idle",
  "simulated": true,
  "uptime_seconds": 30.1
}
```

### `GET /api/v1/system/state`
Compact state view including `controller_authority` and `recovery_status`.

### `GET /api/v1/system/transitions?limit=50`
Returns recorded state transitions, newest first.

### `POST /api/v1/system/state`
Force a transition. Returns **409** for an illegal transition.
```json
{ "state": "DEGRADED", "reason_code": "MANUAL_OVERRIDE", "reason": "operator test" }
```

### `POST /api/v1/system/lockdown?reason=...`
Enter `SAFE_LOCKDOWN` (rejects all actuator commands).

### `POST /api/v1/system/reset`
Exit `SAFE_LOCKDOWN` into `RECOVERY` (the only permitted exit).

---

## Telemetry

### `GET /api/v1/telemetry/latest`
```json
{
  "device_id": "esp32s3-clawsense-01",
  "timestamp": "2026-01-01T12:00:00Z",
  "simulated": true,
  "available": true,
  "age_seconds": 0.4,
  "readings": {
    "temperature_c":    { "sensor": "temperature_c",    "value": 24.16, "unit": "C",    "status": "OK", "simulated": true },
    "humidity_percent": { "sensor": "humidity_percent", "value": 50.26, "unit": "%",    "status": "OK", "simulated": true },
    "motion":           { "sensor": "motion",           "value": false, "unit": "bool", "status": "OK", "simulated": true },
    "light_lux":        { "sensor": "light_lux",        "value": 287.4, "unit": "lux",  "status": "OK", "simulated": true }
  }
}
```
`value` is `null` (never `0`) when a sensor is missing, in error, or not configured.

### `GET /api/v1/telemetry/history?sensor=temperature_c&limit=200`
Returns persisted readings, newest first.

### `POST /api/v1/telemetry/ingest`
Accepts a telemetry push from a device. Runs the full ingestion path
(persistence, event generation, context update, WebSocket broadcast) exactly like
the polling transport. An unconfigured sensor must be sent with
`"status": "NOT_CONFIGURED"` and `"value": null` — never a fabricated `0`.

```json
// request
{
  "device_id": "esp32s3-clawsense-01",
  "simulated": false,
  "readings": {
    "temperature_c":    { "value": 21.5, "unit": "C",    "status": "OK" },
    "humidity_percent": { "value": 44.0, "unit": "%",    "status": "OK" },
    "third_sensor":     { "value": null, "unit": "",     "status": "NOT_CONFIGURED" }
  }
}
```
```json
// response
{ "accepted": true, "device_id": "esp32s3-clawsense-01", "readings": 3, "events_generated": 2 }
```

---

## Safety

### `GET /api/v1/safety/latest`
The most recent safety decision (full per-check detail).

### `GET /api/v1/safety/decisions?limit=50`
Decision history.

### `GET /api/v1/safety/decisions/{decision_id}`
A single decision, or **404**.

### `POST /api/v1/safety/validate`
**Dry run** — validates a raw payload and returns the decision without
dispatching anything.```json
// request
{ "proposal_id": "p-1", "action": "servo_move", "parameters": { "angle_degrees": 250 }, "source": "agent" }
```
```json
// response (abridged)
{
  "decision_id": "…",
  "proposal_id": "p-1",
  "approved": false,
  "reason_code": "ANGLE_OUT_OF_RANGE",
  "reason": "Servo angle 250 is outside the allowed range 0-180 degrees.",
  "checks": { "schema": "PASS", "allow_list": "PASS", "parameter_types": "PASS", "range": "FAIL", "context_freshness": "PASS", "system_state": "PASS", "cooldown": "PASS", "duplicate": "PASS" },
  "check_results": [
    { "name": "range", "status": "FAIL", "detail": "Servo angle 250 is outside the allowed range 0-180 degrees.", "code": "ANGLE_OUT_OF_RANGE", "timestamp": "…", "proposal_id": "p-1" }
  ],
  "dispatch_attempted": false
}
```

---

### `POST /api/v1/safety/test`
Runs the six **predefined** safety tests against the real supervisor and returns
a pass/fail report. This is explicitly a *software validation* test, not a
hardware test.

```json
{
  "kind": "software_validation",
  "hardware_tested": false,
  "total": 6,
  "passed": 6,
  "results": [
    {
      "key": "out_of_range_servo_angle",
      "name": "Out-of-range servo angle (250 degrees)",
      "payload": { "action": "servo_move", "parameters": { "angle_degrees": 250 }, "source": "agent" },
      "system_state": "ONLINE_AGENT",
      "expected": { "approved": false, "reason_codes": ["ANGLE_OUT_OF_RANGE"] },
      "result": { "approved": false, "reason_code": "ANGLE_OUT_OF_RANGE", "checks": { "range": "FAIL" }, "dispatch_attempted": false },
      "passed": true
    }
  ]
}
```

The six tests are: valid servo command, out-of-range servo angle (250°), unknown
action, malformed command, invalid operating state, duplicate/too-frequent
command.

### `GET /api/v1/safety/events?limit=100`
Safety-related audit events (categories `safety_approval` and `safety_rejection`).

---

## Decisions

The plan suggests decision-oriented paths; these are aliases over the same logic.

### `POST /api/v1/decisions/propose`
Alias of `POST /api/v1/actions/propose`.
### `GET /api/v1/decisions?limit=50`
### `GET /api/v1/decisions/{decision_id}` — or **404**

---

## Actions and commands

### `POST /api/v1/actions/propose`
Submit an operator proposal. Well-formed proposals are validated by the
supervisor; malformed ones are rejected at the API boundary with **422**.
```json
{ "action": "servo_move", "parameters": { "angle_degrees": 90 }, "reason": "position sensor" }
```
```json
{
  "proposal": { "proposal_id": "…", "action": "servo_move", "parameters": { "angle_degrees": 90 }, "source": "operator" },
  "decision": { "approved": true, "reason_code": "APPROVED", "checks": { "…": "PASS" } },
  "command": { "command_id": "…", "status": "STATE_CONFIRMED", "action": "servo_move" }
}
```
When rejected, `command` is `null`.

### `GET /api/v1/actions/proposals?limit=50`
### `GET /api/v1/actions/commands?limit=50`
### `GET /api/v1/actions/commands/{command_id}` — or **404**
### `GET /api/v1/actions/latest` — `{ decision, command }`

Command statuses: `PROPOSED`, `VALIDATED`, `APPROVED`, `DISPATCHED`,
`ACKNOWLEDGED`, `STATE_CONFIRMED`, `REJECTED`, `FAILED`, `TIMEOUT`, `UNCERTAIN`.

Each command carries an `expires_at` (TTL `CLAWSENSE_COMMAND_TTL_SECONDS`,
default 10 s). A command that reaches dispatch after its expiry is marked
`FAILED` with `error: COMMAND_EXPIRED` and is **never** sent to the device — this
guards against stale/duplicate execution.

---

## Events

### `GET /api/v1/events`
Query parameters: `category`, `severity`, `event_type`, `device_id`,
`proposal_id`, `command_id`, `search`, `limit` (1–500, default 50), `offset`.
```json
{
  "items": [
    {
      "event_id": "…",
      "timestamp": "2026-01-01T12:00:00Z",
      "event_type": "ACTION_REJECTED",
      "category": "safety_rejection",
      "source": "safety_supervisor",
      "severity": "warning",
      "device_id": "esp32s3-clawsense-01",
      "proposal_id": "…",
      "command_id": null,
      "details": { "reason_code": "ANGLE_OUT_OF_RANGE" },
      "simulated": true
    }
  ],
  "total": 128, "limit": 50, "offset": 0
}
```

### `GET /api/v1/events/stats` — counts by category
### `GET /api/v1/events/export.csv` — CSV download (honours `category`, `severity`)
### `GET /api/v1/events/{event_id}` — or **404**

---

## Simulation controls

Only meaningful in simulation mode. Namespaced under `/simulation`.

### `GET /api/v1/simulation/state`
Device/agent/failure state, including the simulated actuator positions.

### `POST /api/v1/simulation/scenario`
`{"scenario": "normal" | "heatwave" | "cold" | "motion" | "high_humidity" | "sensor_fault" | "stale"}`

### `POST /api/v1/simulation/agent`
`{"mode": "auto" | "unsafe_angle" | "led_alert" | "noop"}`
(`unsafe_angle` makes the agent propose 250° to demonstrate rejection.)

### `POST /api/v1/simulation/agent/availability`
`{"available": false}` forces the agent offline so the system degrades and the
local fallback takes over.

### `POST /api/v1/simulation/failure`
`{"mode": "none" | "timeout" | "reject" | "uncertain"}` — injects device failure.

---

## WebSocket

`ws://localhost:8000/ws`

Every message: `{ "type": string, "data": object, "seq": number }`.

| Type | Payload |
| --- | --- |
| `snapshot` | `{ system, telemetry, decision, command, events, simulated, mode }` — sent on connect |
| `telemetry` | a `TelemetrySnapshot` |
| `event` | an `EventRecord` |
| `decision` | a `SafetyResult` |
| `command` | a `CommandRecord` |
| `system` | a `SystemStatus` |
| `pong` | reply to a client `{"type":"ping"}` |

Slow clients are dropped from the fan-out rather than blocking the control loop.

---

## Error responses

| Status | Meaning |
| --- | --- |
| 404 | resource not found |
| 409 | illegal state transition |
| 422 | request failed validation (unknown action, bad parameter shape) |

---

## Firmware HTTP contract

The ESP32-S3 exposes the endpoints the backend's HTTP transport expects:

| Method | Path | Response |
| --- | --- | --- |
| `GET` | `/health` | `{"status":"ok","firmware":"…","state":"…"}` |
| `GET` | `/telemetry` | `{"device_id","timestamp","simulated":false,"readings":{…}}` |
| `POST` | `/command` | `{"acknowledged","state_confirmed","detail","reported_state"}` |

`POST /command` body: `{"action":"servo_move","parameters":{"angle_degrees":90}}`.
The firmware re-validates the command and returns `acknowledged:false` if its own
supervisor rejects it.
