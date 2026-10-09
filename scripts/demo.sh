#!/usr/bin/env bash
#
# ClawSense guided demo (PLAN.md section 24).
#
# Drives the running backend through the headline scenarios and prints the
# resulting decisions, transitions, commands and events. Requires a running
# backend and python3 (used for JSON extraction). No jq dependency.
#
#   ./scripts/demo.sh [BASE_URL]
#
set -uo pipefail

BASE="${1:-http://localhost:8000}"
API="${BASE}/api/v1"

json_get() {
  # $1: a python expression referencing the parsed object as `d`
  python3 -c "import sys,json
try:
    d = json.load(sys.stdin)
except Exception:
    print('<no json>'); raise SystemExit
print($1)"
}

hr() { printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; }

# ---------------------------------------------------------------------------
hr "0. Backend health"
if ! curl -sf "${API}/health" -o /tmp/clawsense_health.json; then
  echo "ERROR: backend not reachable at ${BASE}."
  echo "Start it first, e.g.:"
  echo "  cd backend && CLAWSENSE_DEGRADED_TIMEOUT_SECONDS=2 CLAWSENSE_OFFLINE_TIMEOUT_SECONDS=4 \\"
  echo "    CLAWSENSE_SIMULATOR_INTERVAL_SECONDS=0.5 .venv/bin/uvicorn app.main:app --port 8000"
  exit 1
fi
cat /tmp/clawsense_health.json | json_get "'status='+str(d['status'])+'  mode='+str(d['mode'])+'  simulated='+str(d['simulated'])+'  state='+str(d['current_state'])"

# ---------------------------------------------------------------------------
hr "1. The AI proposes an unsafe action (250 degrees)"
curl -s -X POST "${API}/simulation/agent/availability" -H 'Content-Type: application/json' \
  -d '{"available":true}' >/dev/null
curl -s -X POST "${API}/simulation/agent" -H 'Content-Type: application/json' \
  -d '{"mode":"unsafe_angle"}' >/dev/null
echo "Agent mode set to 'unsafe_angle'. Waiting for the next control cycle..."
sleep 2
curl -s "${API}/safety/latest" | json_get "'approved='+str(d['approved'])+'  reason_code='+str(d['reason_code'])+'\nchecks='+str(d['checks'])"
echo "-> Rejected before any command was created. The servo never moved."

# ---------------------------------------------------------------------------
hr "2. Dry-run validation (no dispatch)"
curl -s -X POST "${API}/safety/validate" -H 'Content-Type: application/json' \
  -d '{"proposal_id":"demo-dry-run","action":"servo_move","parameters":{"angle_degrees":250},"source":"agent"}' \
  | json_get "'approved='+str(d['approved'])+'  reason_code='+str(d['reason_code'])+'  dispatch_attempted='+str(d['dispatch_attempted'])"

# ---------------------------------------------------------------------------
hr "3. The AI service goes offline -> deterministic local fallback"
curl -s -X POST "${API}/simulation/agent" -H 'Content-Type: application/json' \
  -d '{"mode":"auto"}' >/dev/null
curl -s -X POST "${API}/simulation/scenario" -H 'Content-Type: application/json' \
  -d '{"scenario":"heatwave"}' >/dev/null
curl -s -X POST "${API}/simulation/agent/availability" -H 'Content-Type: application/json' \
  -d '{"available":false}' >/dev/null
echo "Agent forced offline; scenario=heatwave. Waiting for degrade -> offline..."

last=""
for _ in $(seq 1 40); do
  state=$(curl -s "${API}/system/state" | json_get "d['current_state']")
  if [ "$state" != "$last" ]; then echo "  state: ${state}"; last="$state"; fi
  [ "$state" = "OFFLINE_LOCAL" ] && break
  sleep 0.5
done

echo "Transitions:"
curl -s "${API}/system/transitions?limit=5" | python3 -c "
import sys,json
for t in json.load(sys.stdin)['items']:
    print('  %-14s -> %-14s %s' % (t['previous_state'], t['new_state'], t['reason_code']))"

echo "Fallback commands (no LLM involved):"
curl -s "${API}/actions/commands?limit=5" | python3 -c "
import sys,json
for c in json.load(sys.stdin)['items']:
    print('  %-16s %-28s %s' % (c['action'], json.dumps(c['parameters']), c['status']))"

# ---------------------------------------------------------------------------
hr "4. Recovery"
curl -s -X POST "${API}/simulation/agent/availability" -H 'Content-Type: application/json' \
  -d '{"available":true}' >/dev/null
curl -s -X POST "${API}/simulation/scenario" -H 'Content-Type: application/json' \
  -d '{"scenario":"normal"}' >/dev/null
echo "Agent restored. Waiting for recovery..."
for _ in $(seq 1 40); do
  state=$(curl -s "${API}/system/state" | json_get "d['current_state']")
  echo "  state: ${state}"
  [ "$state" = "ONLINE_AGENT" ] && break
  sleep 0.25
done

# ---------------------------------------------------------------------------
hr "5. Device failure is never reported as success"
# Put the agent in no-op mode so it stops issuing servo moves, then let the
# per-action cooldown clear so this test exercises the device path, not cooldown.
curl -s -X POST "${API}/simulation/agent" -H 'Content-Type: application/json' \
  -d '{"mode":"noop"}' >/dev/null
curl -s -X POST "${API}/simulation/failure" -H 'Content-Type: application/json' \
  -d '{"mode":"timeout"}' >/dev/null
echo "Failure mode=timeout. Waiting for the action cooldown to clear..."
sleep 4
curl -s -X POST "${API}/actions/propose" -H 'Content-Type: application/json' \
  -d '{"action":"servo_move","parameters":{"angle_degrees":100},"reason":"demo device failure"}' \
  | json_get "'decision.approved='+str(d['decision']['approved'])+'  reason_code='+str(d['decision']['reason_code'])+'  command.status='+str((d['command'] or {}).get('status'))+'  command.error='+str((d['command'] or {}).get('error'))"
curl -s -X POST "${API}/simulation/failure" -H 'Content-Type: application/json' \
  -d '{"mode":"none"}' >/dev/null
echo "-> The command is TIMEOUT/FAILED, never a false success."

# ---------------------------------------------------------------------------
hr "6. Safe lockdown blocks everything"
curl -s -X POST "${API}/system/lockdown" >/dev/null
curl -s -X POST "${API}/actions/propose" -H 'Content-Type: application/json' \
  -d '{"action":"servo_move","parameters":{"angle_degrees":45},"reason":"demo lockdown"}' \
  | json_get "'decision.approved='+str(d['decision']['approved'])+'  reason_code='+str(d['decision']['reason_code'])+'  command='+str(d['command'])"
curl -s -X POST "${API}/system/reset" >/dev/null
echo "-> Operator reset returned the system to RECOVERY."

# ---------------------------------------------------------------------------
hr "7. Audit log summary"
curl -s "${API}/events/stats" | python3 -c "
import sys,json
for k,v in sorted(json.load(sys.stdin)['by_category'].items()):
    print('  %-20s %d' % (k, v))"
echo ""
echo "Export the full audit log:"
echo "  curl -s '${API}/events/export.csv' -o clawsense-events.csv"
echo ""
echo "Demo complete."
