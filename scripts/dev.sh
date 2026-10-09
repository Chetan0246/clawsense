#!/usr/bin/env bash
#
# ClawSense development launcher.
#
# Starts the FastAPI backend and the Vite dashboard together, and shuts both
# down cleanly on Ctrl-C. Intended for local development only.
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${CLAWSENSE_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "Shutting down ClawSense..."
  [ -n "${FRONTEND_PID}" ] && kill "${FRONTEND_PID}" 2>/dev/null || true
  [ -n "${BACKEND_PID}" ] && kill "${BACKEND_PID}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# --- backend -----------------------------------------------------------------
cd "${ROOT}/backend"

if [ ! -d ".venv" ]; then
  echo "Creating backend virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -e ".[dev]"
fi

# Fast timeouts so state transitions are visible during development.
export CLAWSENSE_DEGRADED_TIMEOUT_SECONDS="${CLAWSENSE_DEGRADED_TIMEOUT_SECONDS:-2}"
export CLAWSENSE_OFFLINE_TIMEOUT_SECONDS="${CLAWSENSE_OFFLINE_TIMEOUT_SECONDS:-4}"
export CLAWSENSE_SIMULATOR_INTERVAL_SECONDS="${CLAWSENSE_SIMULATOR_INTERVAL_SECONDS:-0.5}"

echo "Starting backend on http://localhost:${BACKEND_PORT} ..."
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${BACKEND_PORT}" &
BACKEND_PID=$!

# --- frontend ----------------------------------------------------------------
cd "${ROOT}/frontend"

if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install --no-audit --no-fund
fi

echo "Starting dashboard on http://localhost:${FRONTEND_PORT} ..."
npm run dev -- --port "${FRONTEND_PORT}" &
FRONTEND_PID=$!

echo ""
echo "ClawSense is starting:"
echo "  Dashboard : http://localhost:${FRONTEND_PORT}"
echo "  API docs  : http://localhost:${BACKEND_PORT}/docs"
echo "  Health    : http://localhost:${BACKEND_PORT}/api/v1/health"
echo ""
echo "Press Ctrl-C to stop."
echo ""

wait
