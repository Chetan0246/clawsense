# Limitations

ClawSense is a research and demonstration prototype. This document states
honestly what it does **not** do, so the safety argument is not overstated.

## Safety and certification

- **Not certified.** The design does not implement IEC 61508, ISO 26262,
  IEC 61511, or any functional-safety standard. There is no SIL/ASIL claim.
- **No hardware safety interlock.** There is no independent emergency stop, no
  hardware watchdog on the actuator power path, and no redundant channel. A stuck
  relay or a failed servo driver is not detected.
- **Software cannot replace physical protection.** Fusing, current limiting, a
  correctly rated separate servo supply, and a common ground are the operator's
  responsibility. See [`wiring.md`](wiring.md).
- **Single point of failure in the host.** If the process running the backend is
  compromised, the backend safety supervisor is compromised. Only the on-device
  supervisor remains as an independent boundary.

## Security

- **No authentication or authorisation.** All API endpoints and the WebSocket are
  open. There is no user model, no API-key check, and no rate limiting at the
  transport layer. Do not expose this to an untrusted network.
- **No transport security.** HTTP/WS are plaintext. TLS termination would be the
  operator's responsibility.
- **Firmware WiFi credentials** are read from an uncommitted `secrets.h`; the
  firmware does not implement secure boot, flash encryption, or signed OTA
  updates.

## Functional scope

- **The ESPClaw/LLM integration is an adapter.** The real ESPClaw API has not
  been verified against this codebase. `EspClawAgent` documents the expected
  contract (`POST {endpoint}/propose`) and fails closed when the endpoint is
  unset or unreachable. Until verified against a live ESPClaw instance, the
  agent is exercised through `SimulatedAgent`.
- **The simulated agent is not an LLM.** It uses simple deterministic rules. The
  project's contribution is the supervisory architecture, not agent intelligence.
- **Firmware is not hardware-tested here.** The firmware is written to compile
  under PlatformIO for `esp32-s3-devkitc-1` but has not been flashed or validated
  on physical hardware in this environment. Sensor calibrations are generic
  defaults and must be re-calibrated.
- **Single device.** There is no fleet management, device provisioning, or
  multi-device coordination. `device_id` exists but only one device is modelled.
- **Sensor set is fixed.** Temperature, humidity, motion, and light are
  hard-coded; adding a sensor requires code changes on both sides.
- **Persistence is single-node SQLite.** No replication, no migration framework,
  no retention policy — the database grows until it is pruned or deleted.

## Operational

- **No real-time guarantees.** The control loop runs at a best-effort cadence; it
  is not an RTOS and makes no latency bound guarantees.
- **No time synchronisation guarantee.** The firmware uses NTP when available and
  falls back to `millis()`; timestamps across devices are not guaranteed to be
  comparable at high precision.
- **The fallback controller is intentionally simple.** Its rules are documented
  and conservative, not optimal. It may hold a non-ideal actuator state rather
  than compute a better one.
- **Cooldown and duplicate windows are global per action**, not per context; this
  is deliberate (fail closed) but can suppress a legitimate rapid repeat.

## What is genuinely in scope

Within the above boundaries, the following are implemented and tested:

- Deterministic, fail-closed validation independent of the LLM.
- Explicit, observable state transitions and recovery.
- A documented local fallback that works with no network or LLM.
- A command lifecycle that never reports approval as physical success.
- A correlated, exportable audit log.
- Two independent validators (backend and device) enforcing the same limits.
