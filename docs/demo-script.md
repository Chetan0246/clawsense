# Demo script

A ~5-minute walkthrough that exercises the full supervisory architecture. It can
be driven from the dashboard or entirely from the shell with
[`scripts/demo.sh`](../scripts/demo.sh).

## Setup

```bash
# Terminal 1 — backend (fast timeouts make the demo snappy)
cd backend
CLAWSENSE_DEGRADED_TIMEOUT_SECONDS=2 \
CLAWSENSE_OFFLINE_TIMEOUT_SECONDS=4 \
CLAWSENSE_SIMULATOR_INTERVAL_SECONDS=0.5 \
.venv/bin/uvicorn app.main:app --port 8000

# Terminal 2 — dashboard
cd frontend && npm run dev      # http://localhost:5173
```

The dashboard shows a persistent **SIMULATION MODE** banner: every value is
simulated, not hardware.

---

## Act 1 — Normal operation

**Show:** Overview. State is `ONLINE_AGENT`, authority is `agent`. Sensor cards
update live; the temperature chart scrolls.

**Narration:** "The agent observes the context summary and proposes actions. Each
proposal is recorded before anything else happens."

---

## Act 2 — The AI proposes something unsafe

**Dashboard:** System Health → Simulation Controls → Agent Mode → **unsafe_angle**.

**Shell equivalent:**
```bash
curl -s -X POST localhost:8000/api/v1/simulation/agent \
  -H 'Content-Type: application/json' -d '{"mode":"unsafe_angle"}'
```

**Show:** Safety Center → Latest Decision.

**Result:** `REJECTED`, `reason_code: ANGLE_OUT_OF_RANGE`, with the check table:
`schema PASS`, `allow_list PASS`, `parameter_types PASS`, `range FAIL`.

**Narration:** "The agent asked for 250°. The deterministic supervisor rejected
it. No command was created and the servo never moved. Notice the rejection is
recorded with the exact check that failed."

**Verify:** AITrace shows the proposal with **no command** attached.

---

## Act 3 — Dry-run any action

**Dashboard:** Safety Center → Dry-Run Validation. Choose `servo_move`, set the
angle to `250`, source `agent`, click **Validate**.

**Narration:** "Operators can exercise the supervisor without dispatching
anything. This is the same code path the live system uses."

---

## Act 4 — The AI service goes away

**Dashboard:** System Health → **Force agent offline**.

**Shell equivalent:**
```bash
curl -s -X POST localhost:8000/api/v1/simulation/agent/availability \
  -H 'Content-Type: application/json' -d '{"available":false}'
# optional: make it dramatic
curl -s -X POST localhost:8000/api/v1/simulation/scenario \
  -H 'Content-Type: application/json' -d '{"scenario":"heatwave"}'
```

**Show:** System Health → State Machine and Transition History.

**Result over a few seconds:**
1. `ONLINE_AGENT → DEGRADED` (`AGENT_UNREACHABLE`)
2. `DEGRADED → OFFLINE_LOCAL` (`AGENT_UNREACHABLE_PERSISTENT`)
3. Authority switches to **local**; `FALLBACK_ACTIVATED` events appear.

**Show:** Overview → Latest Command. The deterministic fallback has issued
`set_status_led {color: red}` and `buzzer_beep {duration_ms: 500}`, both
`STATE_CONFIRMED`.

**Narration:** "No LLM is involved now. The local rules took over, and their
output still passed through the same safety supervisor. This is the offline
fallback."

---

## Act 5 — Recovery

**Dashboard:** **Restore agent**.

**Show:** Transitions `OFFLINE_LOCAL → RECOVERY` (`CONNECTIVITY_RESTORED`) then
`RECOVERY → ONLINE_AGENT` (`RECOVERY_COMPLETED`). Authority returns to `agent`.

**Narration:** "Recovery is explicit and observable — the system does not jump
straight back to trusting the agent."

---

## Act 6 — Device failure is not reported as success

**Dashboard:** Simulation Controls → Device Failure Injection → **timeout**, then
submit a valid action (e.g. Safety Center dry run won't dispatch, so use
Overview or the shell):

```bash
curl -s -X POST localhost:8000/api/v1/actions/propose \
  -H 'Content-Type: application/json' \
  -d '{"action":"set_status_led","parameters":{"color":"green"},"reason":"demo"}'
```

**Result:** the command ends `TIMEOUT` (or `FAILED` / `UNCERTAIN`), a
`DEVICE_TIMEOUT` event is recorded, and the system degrades. **It never claims
the action succeeded.**

Reset the injection to **none** afterwards.

---

## Act 7 — Safe lockdown and the audit log

**Dashboard:** System Health → **Trigger Safe Lockdown**. Then try any action:
it is rejected with `INVALID_SYSTEM_STATE`. **Clear Fault** returns to
`RECOVERY`.

**Show:** Event History — filter by `safety_rejection`, search by proposal id,
and click **Export CSV** to download the audit trail.

**Narration:** "Every proposal, decision, dispatch and acknowledgement is
correlated by proposal and command id, and exportable."

---

## Reset between runs

```bash
rm -f backend/data/clawsense.sqlite3
```

---

## One-command version

```bash
./scripts/demo.sh            # defaults to http://localhost:8000
```

The script runs Acts 2, 4, 6 and 7 and prints the resulting decisions,
transitions, commands and events.
