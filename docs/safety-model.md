# Safety model

This document states precisely what ClawSense's safety mechanism does, what it
does **not** guarantee, and the assumptions it relies on.

## The safety claim

> An AI-generated action cannot reach an actuator unless it is (a) expressed in a
> fixed, allow-listed schema, (b) within explicit numeric limits, (c) supported by
> fresh context, (d) permitted in the current system state, and (e) validated
> independently a second time on the device.

The mechanism is **deterministic** and has **no dependency on the LLM**. Given
identical inputs and configuration, it always produces the identical decision.

## Fail-closed principle

Any uncertainty results in **rejection or a predefined safe response** — never a
best guess:

- Unparseable agent response → discarded, no action.
- Unknown action name → rejected.
- Malformed or missing parameters → rejected.
- Missing or stale sensor context → rejected for actuator actions.
- Illegal system state → rejected.
- Agent unreachable → degrade, then hand control to the deterministic local rules.
- Device does not acknowledge → the command is `TIMEOUT` / `FAILED` / `UNCERTAIN`,
  **never** reported as success.

## The eight checks

Evaluated in order; every check is reported independently (status, explanation,
timestamp, associated proposal id). The decision is `approved` only if no check
fails. `SKIP` means a check could not be evaluated because an earlier check
already failed; a `SKIP` never counts as a pass.

| # | Check | PASS when | Fails with code |
| --- | --- | --- | --- |
| 1 | `schema` | payload is an object with `proposal_id`, `action` (non-empty string), `parameters` (object), `source` | `SCHEMA_INVALID` |
| 2 | `allow_list` | `action` ∈ `{servo_move, buzzer_beep, set_status_led, no_op}` | `UNKNOWN_ACTION` |
| 3 | `parameter_types` | parameters match the action's schema exactly (no missing, wrong-typed, or extra keys) | `INVALID_PARAMETERS` |
| 4 | `range` | `0 ≤ angle_degrees ≤ 180`; `1 ≤ duration_ms ≤ 2000` | `ANGLE_OUT_OF_RANGE`, `DURATION_OUT_OF_RANGE` |
| 5 | `context_freshness` | for `servo_move` / `buzzer_beep`: context exists and age ≤ `context_max_age_seconds` | `CONTEXT_MISSING`, `CONTEXT_STALE` |
| 6 | `system_state` | the proposal's `source` is permitted to drive actuators in the current state | `INVALID_SYSTEM_STATE` |
| 7 | `cooldown` | the same action has not run within `action_cooldown_seconds` | `COOLDOWN_ACTIVE` |
| 8 | `duplicate` | no identical action + parameters within the cooldown window | `DUPLICATE_COMMAND` |

Example — an agent proposes a servo angle of 250°:

```json
{
  "approved": false,
  "reason_code": "ANGLE_OUT_OF_RANGE",
  "checks": {
    "schema": "PASS",
    "allow_list": "PASS",
    "parameter_types": "PASS",
    "range": "FAIL",
    "context_freshness": "PASS",
    "system_state": "PASS",
    "cooldown": "PASS",
    "duplicate": "PASS"
  }
}
```

## Source ↔ state authority matrix

| System state | agent | fallback | operator | simulator |
| --- | :---: | :---: | :---: | :---: |
| `ONLINE_AGENT` | ✅ | ✅ | ✅ | ✅ |
| `DEGRADED` | ✅ | ✅ | ✅ | ✅ |
| `OFFLINE_LOCAL` | ❌ | ✅ | ✅ | ✅ |
| `RECOVERY` | ❌ | ✅ | ✅ | ✅ |
| `SAFE_LOCKDOWN` | ❌ | ❌ | ❌ | ❌ |

`SAFE_LOCKDOWN` rejects **all** actuator commands and has no automatic exit.

## Why two independent validators

The backend supervisor and the on-device firmware supervisor are separate
implementations that enforce the same limits. This means:

- A bug in the backend cannot by itself drive an actuator out of range.
- A compromised or buggy agent cannot bypass the device's own checks.
- The device remains safe even if the network link is delivering crafted input.

## Command lifecycle — approval ≠ execution

An approved backend action is **not** proof of a physical action. Each stage is
tracked separately:

```
PROPOSED → VALIDATED → APPROVED → DISPATCHED → ACKNOWLEDGED → STATE_CONFIRMED
                                        │
                                        ├─▶ TIMEOUT      (no acknowledgement in time)
                                        ├─▶ FAILED       (device rejected)
                                        └─▶ UNCERTAIN    (communication uncertainty)
```

On any failure the system degrades; it never silently claims success.

## Safe state on communication loss

- Buzzer: **OFF**
- Status LED: **OFF**, or driven by the local fallback rule
- Servo: **holds its last position** (never forced to a new position, never left
  driving against a stop)

See [`wiring.md`](wiring.md) for the rationale.

## Assumptions and threat model

The safety argument relies on:

1. The device's own supervisor is correct and is the last code to touch a GPIO.
2. Physical protection (fuses, current limiting, a correctly rated separate servo
   supply, common ground) exists. **Software cannot replace it.**
3. Sensor values are plausible; calibration is the operator's responsibility.
4. The host running the backend is trusted. There is **no authentication layer**
   in this prototype.

In scope: preventing an LLM (or a buggy/malicious agent response) from driving an
actuator outside safe limits, in an illegal state, with stale context, or at an
unsafe rate.

**Out of scope:** protection against a physically faulty actuator, a compromised
device, mains-voltage loads, real-time deadlines, and any certified functional
safety requirement (IEC 61508 / ISO 26262 / IEC 61511). See
[`limitations.md`](limitations.md).

## How this is verified

Every check has dedicated tests, including the explicit failure cases required by
the plan (250° angle, negative angle, unknown action, malformed payload, wrong
type, missing parameter, invalid state, stale context, cooldown, duplicate). See
[`testing.md`](testing.md).

```bash
cd backend && .venv/bin/python -m pytest
```
