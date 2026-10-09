# Testing

## Running the tests

```bash
cd backend
.venv/bin/python -m pytest          # 78 tests
.venv/bin/python -m pytest -v       # verbose
```

Frontend type-check and production build:

```bash
cd frontend
npm run build                       # runs `tsc --noEmit && vite build`
```

The suite uses an in-memory SQLite database and the simulated device/agent, so it
is fast (< 5 s), deterministic, and needs no hardware or network.

---

## Test matrix

### `tests/test_safety_supervisor.py` — 23 tests
The deterministic safety supervisor in isolation.

| Area | Cases |
| --- | --- |
| Happy path | valid servo approved; `no_op` approved without context |
| Range | **250° rejected** (`ANGLE_OUT_OF_RANGE`); negative angle rejected; boundary 0° and 180° accepted; buzzer duration out of range rejected |
| Allow-list | **unknown action rejected** (`UNKNOWN_ACTION`) |
| Schema | **non-object payload rejected**; **missing required fields rejected** |
| Parameters | **wrong type rejected**; **missing parameter rejected**; **extra/unknown parameter rejected**; invalid LED colour rejected |
| Context | **stale context rejected** (`CONTEXT_STALE`); **missing context rejected** (`CONTEXT_MISSING`) |
| State | `SAFE_LOCKDOWN` rejects all; agent rejected in `OFFLINE_LOCAL`; fallback allowed in `OFFLINE_LOCAL` |
| Rate | cooldown blocks rapid repeat; allowed after the window; different parameters are not duplicates |
| Invariants | validation is deterministic; all eight checks are always reported |

### `tests/test_state_machine.py` — 10 tests
- Initial state and controller authority.
- Legal transitions applied; illegal and self-transitions refused.
- Agent failure → `DEGRADED` → `OFFLINE_LOCAL` with correct reason codes.
- `OFFLINE_LOCAL → RECOVERY → ONLINE_AGENT` on recovery.
- `RECOVERY → OFFLINE_LOCAL` when health checks fail.
- Lockdown from any state; no automatic exit; operator reset to `RECOVERY`.
- Quick `DEGRADED → ONLINE_AGENT` recovery.

### `tests/test_fallback_controller.py` — 8 tests
- High temperature → red LED + bounded buzzer.
- Low temperature → yellow LED.
- High humidity → yellow LED.
- Motion → observation servo angle.
- Nominal → `no_op`.
- No context → safe `no_op` (never invents actuator commands).
- Fallback proposals pass the supervisor in `OFFLINE_LOCAL`.
- Fallback respects a reduced `servo_max_degrees`.

### `tests/test_api.py` — 23 tests
- Health, readiness, system status/state.
- Simulation controls (scenario/agent/failure) and 422 on invalid input.
- `POST /safety/validate` dry run returns the rejection.
- Unknown action rejected at the API boundary (422).
- Live telemetry flagged `simulated: true`; telemetry history.
- Events recorded, filterable, exportable as CSV, with stats; 404 for unknown id.
- Valid proposal approved and dispatched; unsafe proposal rejected with no command.
- Commands list and `/actions/latest`.
- Lockdown / reset / illegal transition (409).
- Transitions recorded.
- WebSocket snapshot + ping/pong.
- `POST /telemetry/ingest` accepts a push (and 422 on a bad payload), preserving `simulated: false`.
- `POST /safety/test` runs the six predefined tests — all pass, `hardware_tested: false`.
- `GET /safety/events` returns only approval/rejection events.
- `/decisions` aliases (`propose`, list, get, 404).

### `tests/test_integration.py` — 14 tests
End-to-end across the whole pipeline.

- **Unsafe agent proposal rejected; device unchanged and nothing dispatched.**
- **Agent unavailable → `DEGRADED` → `OFFLINE_LOCAL` → deterministic fallback fires.**
- Device timeout (real hang) → command `TIMEOUT` + audit event.
- Transport-reported timeout → command `TIMEOUT` with `DEVICE_TIMEOUT`.
- Device rejection → command `FAILED` + `DEVICE_REJECTED`.
- Communication uncertainty is never reported as success (`UNCERTAIN`).
- Audit log completeness for rejected and approved proposals.
- `no_op` confirmed without dispatch.
- Cooldown enforced across the pipeline.
- Expired command (TTL) → `FAILED`/`COMMAND_EXPIRED`, never dispatched.
- `SAFE_LOCKDOWN` blocks actuator commands.
- Forced agent offline genuinely degrades, then recovers through `RECOVERY`.
- Stale telemetry fails closed.

---

## Required failure cases (PLAN.md section 7)

| Required case | Covered by |
| --- | --- |
| Valid command accepted | `test_valid_servo_command_is_approved` |
| 250° rejected | `test_servo_angle_250_is_rejected_by_range` |
| Negative angle rejected | `test_servo_negative_angle_is_rejected` |
| Unknown action rejected | `test_unknown_action_is_rejected` |
| Malformed proposal rejected | `test_non_object_payload_is_rejected` |
| Wrong type rejected | `test_wrong_parameter_type_is_rejected` |
| Missing parameter rejected | `test_missing_parameter_is_rejected` |
| Invalid state rejected | `test_safe_lockdown_rejects_all_actions` |
| Stale context rejected | `test_stale_context_is_rejected` |
| Cooldown enforced | `test_cooldown_blocks_rapid_repeat` |
| Duplicate suppressed | `test_cooldown_blocks_rapid_repeat` (duplicate check) |

---

## Hardware test checklist (NOT executed)

No physical hardware was available in this environment, so **no hardware test has
been run**. The firmware has not been compiled or flashed. The table below is the
checklist an operator must complete; every row is currently **NOT RUN**.

| # | Test | Expected | Status |
| --- | --- | --- | --- |
| H1 | Compile firmware | `pio run` succeeds | NOT RUN |
| H2 | Sensor reading (DHT22) | plausible temperature/humidity | NOT RUN |
| H3 | Sensor reading (PIR) | motion edge detected | NOT RUN |
| H4 | Third sensor | `NOT_CONFIGURED` until configured | NOT RUN |
| H5 | OLED update | shows state, sensors, connection | NOT RUN |
| H6 | LEDs | green/yellow/red match state semantics | NOT RUN |
| H7 | Buzzer | bounded beep, off afterwards | NOT RUN |
| H8 | Servo movement | moves within 0–180°, no resets | NOT RUN |
| H9 | Invalid command rejection | on-device supervisor rejects 250° | NOT RUN |
| H10 | Wi-Fi disconnection | node enters `OFFLINE_LOCAL`, local rules run | NOT RUN |
| H11 | Backend shutdown | local safety and fallback continue | NOT RUN |
| H12 | Recovery after reconnect | `RECOVERY` → `ONLINE_AGENT` after health checks | NOT RUN |

Do not claim any hardware behaviour until the corresponding row has been run and
its result recorded.

## Known gaps

- **No hardware validation.** See the checklist above.
- **Firmware is not compiled.** No PlatformIO toolchain was available; the
  firmware has only had a static review. API usage is verified by inspection.
- **ESPClaw integration is unverified.** The adapter documents the expected
  contract but has not been exercised against a live ESPClaw instance.
- **Database-failure handling** is not covered by an automated test. Repositories
  use a locked SQLite connection; a failure would currently surface as an
  exception rather than a degraded mode.
- **No firmware unit tests.** The pure validation/state-transition logic could be
  tested with a PlatformIO `native` environment; that is not implemented.
- **No load/soak testing.** Behaviour under sustained high event rates is
  untested.

---

## Manual verification

```bash
# 1. start the backend, then:
curl -s localhost:8000/api/v1/health | python3 -m json.tool

# 2. unsafe proposal is rejected, no command created
curl -s -X POST localhost:8000/api/v1/actions/propose \
  -H 'Content-Type: application/json' \
  -d '{"action":"servo_move","parameters":{"angle_degrees":250},"reason":"demo"}' \
  | python3 -m json.tool

# 3. dry-run validation
curl -s -X POST localhost:8000/api/v1/safety/validate \
  -H 'Content-Type: application/json' \
  -d '{"proposal_id":"p1","action":"servo_move","parameters":{"angle_degrees":250},"source":"agent"}' \
  | python3 -m json.tool
```

Or run the guided demo: [`demo-script.md`](demo-script.md) / `scripts/demo.sh`.
