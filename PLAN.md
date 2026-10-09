# ClawSense — Complete AI Agent Implementation Plan

## 1. Project Overview

**Project title:** ClawSense: A Context-Aware Agentic IoT System with Deterministic Safety Validation and Offline Fallback on ESP32-S3.

**Project type:** Embedded Systems and IoT, AI-assisted control, hardware-software integration.

**Primary objective:** Build a working IoT prototype and web dashboard that demonstrates how AI-generated actions can be validated by an independent deterministic safety supervisor before hardware execution, with a local fallback controller when the AI service or network is unavailable.

The system must demonstrate:

1. Sensor data acquisition from an ESP32-S3.
2. Event generation and short-term contextual memory.
3. AI-based action proposals through ESPClaw or a verified integration with the configured LLM.
4. Deterministic action validation independent of the LLM.
5. Safe actuator command execution.
6. Local rule-based fallback when the AI service is unavailable.
7. System state transitions, recovery, and audit logging.
8. A professional, responsive web dashboard.

The project is not merely a sensor dashboard, an AI chatbot, or an ESPClaw demonstration.

The main engineering contribution is the ClawSense supervisory control and safety architecture.

---

## 2. Mandatory Development Rules

The coding agent MUST follow these rules.

### 2.1 Inspect before implementing

Before writing code:

- Inspect the existing repository and its files.
- Identify existing ESP32 firmware, ESPClaw setup, libraries, and hardware pin assignments.
- Inspect available documentation for the installed ESPClaw version.
- Determine how ESPClaw exposes sensor tools and invokes actions.
- Preserve working code unless a documented reason requires changing it.
- Record assumptions and unresolved hardware details.

Do not invent ESPClaw APIs, SDK functions, endpoints, libraries, or capabilities.

If the existing ESPClaw installation cannot be integrated immediately, implement a documented adapter interface and a deterministic simulator. Keep the real integration point explicit.

### 2.2 Do not fake functionality

The implementation must distinguish between:

- Real hardware readings.
- Simulated sensor readings.
- Real LLM proposals.
- Simulated AI proposals.
- Actual hardware actions.
- Simulated actions.
- Real device connectivity.
- Simulated connectivity failures.

The dashboard must never report a simulated result as a real hardware result.

Display a persistent `SIMULATION MODE` banner when using simulated data.

### 2.3 Safety requirements

- The LLM must never directly operate GPIO pins.
- The frontend must never directly operate GPIO pins.
- All actuator proposals must pass through deterministic validation.
- The ESP32 must validate actuator commands before execution.
- Rejected actions must not reach the actuator.
- Invalid, missing, stale, or malformed commands must fail closed.
- The offline controller must operate independently of the LLM.
- Network failure must not disable local safety checks.
- Secrets and API keys must never be embedded in frontend source code or committed to Git.

### 2.4 Scope control

Prioritize a reliable, complete vertical slice over unnecessary features.

Do not add Kubernetes, microservices, cloud deployment, authentication providers, complicated message brokers, or other infrastructure unless a genuine requirement emerges.

---

## 3. Hardware and Assumptions

The known hardware includes:

- ESP32-S3 development board.
- DHT22 temperature and humidity sensor.
- PIR motion sensor.
- A third sensor replacing the original LDR.
- OLED display.
- Servo motor, if available and safe to power.
- Buzzer.
- Green, yellow, and red LEDs.
- Push buttons.
- Breadboard and jumper wires.
- Laptop USB as the available power source.

The exact third sensor model, ESP32-S3 pinout, OLED controller, servo availability, and board-specific wiring must be verified before finalizing firmware.

### Hardware rules

1. Create a centralized pin configuration file.
2. Never guess GPIO assignments without inspecting the board and existing wiring.
3. Avoid ESP32-S3 strapping pins, USB pins, flash/PSRAM pins, or other restricted pins when selecting GPIOs.
4. Verify voltage compatibility for every sensor.
5. Ensure common ground where signal and power circuits require it.
6. Never power a servo through an ESP32 GPIO.
7. Test the ESP32 without the servo before connecting it.
8. If the servo causes resets, USB instability, or Wi-Fi disconnections, disconnect it and use the LEDs and buzzer as the actuator demonstration.
9. Do not require an external battery, SD card, RTC, or additional power supply for the basic demo.
10. Do not implement unsupported sensor readings merely to fill dashboard cards.

Implement the third sensor using a configurable sensor interface. Once the actual model is known, implement its correct driver, voltage requirements, units, and validation.

If the third sensor is not yet integrated, display `NOT CONFIGURED` instead of inventing readings.

---

## 4. Technology Stack

Use the following stack unless the repository already contains a working equivalent.

### Frontend

- React.
- Vite.
- TypeScript.
- Tailwind CSS.
- Recharts for telemetry charts.
- Lucide React for icons.
- WebSocket client for live updates.

### Backend

- Python 3.
- FastAPI.
- Pydantic for schema validation.
- SQLAlchemy or a small repository abstraction.
- SQLite for persistent event history.
- WebSockets for real-time updates.
- Pytest for automated tests.

### Embedded firmware

- ESP32-S3.
- Existing compatible ESPClaw installation and libraries.
- Arduino framework or the framework already used by the project.
- A hardware abstraction layer for sensors, outputs, and communications.

Do not rewrite a working ESPClaw firmware installation simply to standardize the framework.

### AI integration

Use the existing, verified ESPClaw integration and its configured LLM provider.

If the existing integration cannot be confirmed, define an `AgentAdapter` interface and implement a deterministic simulator first.

The application must continue to work in simulation mode without an API key.

### Development environment

- Frontend: Vite development server.
- Backend: Uvicorn.
- Firmware: compatible ESP32-S3 development and flashing workflow.
- Repository: Git.

Do not require public cloud hosting for local demonstration.

---

## 5. Required Architecture

Implement the following logical architecture.

```text
DHT22 + PIR + Configured Third Sensor
                  |
                  v
            ESP32-S3 Firmware
                  |
                  v
          Sensor/Event Ingestion
                  |
                  v
           Contextual Memory
                  |
                  v
          ESPClaw / Agent Adapter
                  |
                  v
           Action Proposal
                  |
                  v
       ClawSense Safety Supervisor
                  |
          +-------+-------+
          |               |
       APPROVE           REJECT
          |               |
          v               v
    Device Command    Audit Event
          |
          v
   ESP32-S3 Validation
          |
          v
       Actuator
          
Backend --> SQLite --> REST API / WebSocket --> React Dashboard
```

The offline architecture must work independently:

```text
Agent or Network Failure
          |
          v
      DEGRADED
          |
          v
     OFFLINE_LOCAL
          |
          v
    Local Rule Engine
          |
          v
 ESP32 Safety Validation
          |
          v
     Safe Output
```

The ESP32 must not depend on a continuously available backend or LLM to enforce local safety constraints.

---

## 6. Repository Structure

Create or adapt the repository to the following structure.

```text
clawsense/
├── plan.md
├── README.md
├── .gitignore
├── .env.example
├── docker-compose.yml                 # Optional, local development only
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   ├── cards/
│   │   │   ├── charts/
│   │   │   ├── safety/
│   │   │   └── events/
│   │   ├── pages/
│   │   │   ├── Overview.tsx
│   │   │   ├── LiveSensors.tsx
│   │   │   ├── AITrace.tsx
│   │   │   ├── SafetyCenter.tsx
│   │   │   ├── SystemHealth.tsx
│   │   │   └── EventHistory.tsx
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── types/
│   │   └── main.tsx
│   └── tests/
│
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── telemetry.py
│   │   │   ├── decisions.py
│   │   │   ├── safety.py
│   │   │   ├── system.py
│   │   │   └── events.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── safety_supervisor.py
│   │   │   ├── state_machine.py
│   │   │   ├── event_engine.py
│   │   │   ├── context_memory.py
│   │   │   ├── fallback_controller.py
│   │   │   ├── command_dispatcher.py
│   │   │   └── agent_adapter.py
│   │   ├── repositories/
│   │   ├── transports/
│   │   └── db/
│   └── tests/
│       ├── test_safety.py
│       ├── test_state_machine.py
│       ├── test_fallback.py
│       ├── test_api.py
│       └── test_integration.py
│
├── firmware/
│   ├── README.md
│   ├── platformio.ini                 # If using PlatformIO
│   ├── include/
│   │   └── config.h
│   ├── src/
│   │   ├── main.cpp
│   │   ├── sensor_manager.cpp
│   │   ├── event_engine.cpp
│   │   ├── safety_supervisor.cpp
│   │   ├── local_controller.cpp
│   │   ├── state_machine.cpp
│   │   ├── actuator_manager.cpp
│   │   ├── communication.cpp
│   │   └── display_manager.cpp
│   └── test/
│
├── docs/
│   ├── architecture.md
│   ├── wiring.md
│   ├── safety-model.md
│   ├── api-reference.md
│   ├── testing.md
│   ├── demo-script.md
│   └── limitations.md
│
└── scripts/
    ├── dev.sh
    └── demo_seed.py
```

Adjust the exact layout if existing project files make another structure more practical. Do not create empty placeholder files merely to match this tree.

---

## 7. Frontend Requirements

Build a polished, responsive application called **ClawSense Control Center**.

### Design direction

- Dark industrial/technical dashboard.
- Navy or charcoal background.
- Clear typography.
- Cards with restrained borders.
- Consistent spacing and alignment.
- Green for approved/healthy.
- Yellow or amber for degraded/warning.
- Red for rejected/fault/lockdown.
- Accessible color contrast.
- Responsive desktop, tablet, and mobile layouts.
- Consistent loading, error, and empty states.
- Keyboard-accessible controls.
- Avoid excessive animations and decorative elements.

Do not sacrifice functional correctness for visual effects.

### Page 1: Overview

Display:

- Device connection state.
- Firmware/device identifier.
- Current operating mode.
- Temperature and humidity.
- PIR motion state.
- Third sensor reading and status.
- Latest agent proposal.
- Latest safety decision.
- Actuator state.
- Network/agent health.
- Recent events.
- A small sensor trend chart.

Display sensor units and timestamps.

Mark stale sensor readings as stale. Never display missing values as zero.

### Page 2: Live Sensors

Include:

- Current readings.
- Historical readings.
- Time-series charts.
- Sensor connection/health.
- Last received timestamp.
- Sensor error indicators.
- Configured units and valid ranges.
- Clearly labelled simulated readings when simulation mode is active.

The dashboard must update using WebSockets, with a polling or refresh fallback if appropriate.

### Page 3: AI Decision Trace

Show the complete lifecycle of each action:

1. Triggering event.
2. Relevant sensor context.
3. Recent contextual events.
4. Agent proposal.
5. Structured action payload.
6. Safety checks.
7. Final validation result.
8. Command delivery result.
9. Device acknowledgement, if available.
10. Actual reported actuator state, if available.

Do not claim an action was physically executed just because the backend accepted a request.

Display the agent's explanation as a proposal, not as proof that the explanation is factually correct.

Clearly distinguish a proposed action from an approved action and a confirmed hardware action.

### Page 4: Safety Center

Display each safety check independently.

Required checks:

- Schema validation.
- Command allow-list.
- Parameter/range validation.
- System-state validation.
- Cooldown/rate limit.
- Context freshness.
- Conflicting or duplicate command detection.
- Device acknowledgement/timeout status.

For each check show:

- Status.
- Short explanation.
- Timestamp.
- Associated proposal or event ID.

Provide a **Run Safety Test** button.

The button must call the actual backend safety validation code, not merely update frontend state.

Provide predefined tests:

- Valid servo command.
- Out-of-range servo angle.
- Unknown action.
- Malformed command.
- Invalid operating state.
- Duplicate/too-frequent command.

For the out-of-range test, use a servo angle of 250 degrees against a configured allowed range of 0–180 degrees.

Expected result:

```text
Proposal: servo_move(angle=250)
Schema: PASS
Allow-list: PASS
Range validation: FAIL
Decision: REJECTED
Actuator dispatch: NOT ATTEMPTED
```

Label this as a software validation test unless a real hardware test has been executed.

Never provide a dashboard control that bypasses safety validation.

### Page 5: System Health

Display the system state machine:

- `ONLINE_AGENT`
- `DEGRADED`
- `OFFLINE_LOCAL`
- `RECOVERY`
- `SAFE_LOCKDOWN`

Display:

- Current state.
- Previous state.
- Transition reason.
- Last successful agent request.
- Last successful device communication.
- Current controller authority.
- Agent availability.
- Network availability.
- Last state transition.
- Recovery status.

Use a visible state-transition timeline.

A manually selected simulation state must be labelled simulated and must not be presented as evidence of a real outage.

### Page 6: Event History

Display searchable, filterable, paginated events.

Event categories:

- Sensor reading.
- Sensor threshold/event.
- Context update.
- Agent proposal.
- Safety approval.
- Safety rejection.
- Command dispatch.
- Device acknowledgement.
- Device communication failure.
- Agent timeout.
- State transition.
- Offline fallback.
- Recovery.
- Manual override.
- Configuration change.

Each event should include:

- Unique event ID.
- Timestamp.
- Event type.
- Source.
- Severity.
- Related proposal/command ID.
- Structured details.
- Real or simulated source.

Support CSV export for review evidence.

Never include API keys, access tokens, or other secrets in event records.

---

## 8. Backend Requirements

### 8.1 API

Implement versioned REST endpoints.

Suggested endpoints:

```text
GET  /api/v1/health
GET  /api/v1/system/status
GET  /api/v1/system/transitions

GET  /api/v1/telemetry/latest
GET  /api/v1/telemetry/history

POST /api/v1/telemetry/ingest

POST /api/v1/decisions/propose
GET  /api/v1/decisions
GET  /api/v1/decisions/{decision_id}

POST /api/v1/safety/validate
GET  /api/v1/safety/events
POST /api/v1/safety/test

GET  /api/v1/events
GET  /api/v1/events/export

WS   /api/v1/ws
```

Device-specific command endpoints may be added after verifying the actual communication protocol.

Do not expose a raw unrestricted GPIO endpoint.

All request and response payloads must be validated using Pydantic schemas.

Return useful error messages without exposing stack traces or secrets.

### 8.2 WebSocket

Publish typed events, such as:

```json
{
  "type": "telemetry.updated",
  "source": "esp32",
  "simulated": false,
  "timestamp": "ISO-8601 timestamp",
  "data": {
    "temperature_c": 29.4,
    "humidity_percent": 67.0,
    "motion_detected": true
  }
}
```

The numerical values above are examples, not assumed live readings.

Use separate event types for:

- Telemetry.
- Decision proposals.
- Safety results.
- State transitions.
- Actuator status.
- Device health.

WebSocket clients must not have the authority to execute unvalidated hardware commands.

### 8.3 Configuration

Use environment variables for:

- Database path.
- Application mode.
- Backend host/port.
- LLM provider configuration.
- API keys.
- ESP32 communication configuration.
- Timeouts.
- Sensor thresholds.
- Safety ranges and cooldowns.

Provide `.env.example` with placeholder values only.

Never commit a populated `.env` file.

---

## 9. Structured Action Contract

All agent proposals must use a strict schema.

Example:

```json
{
  "proposal_id": "generated-uuid",
  "action": "servo_move",
  "parameters": {
    "angle_degrees": 90
  },
  "reason": "Illustrative contextual explanation",
  "source": "agent",
  "created_at": "ISO-8601 timestamp"
}
```

Required properties:

- Unique proposal ID.
- Known action name.
- Typed parameters.
- Timestamp.
- Explicit source.
- Optional bounded explanation.

Supported actions should be explicitly allow-listed.

Initial action allow-list:

- `servo_move`
- `buzzer_beep`
- `set_status_led`
- `no_op`

The allowed parameters and safe ranges for each action must be configurable and independently enforced by firmware.

Example servo limits:

```text
Minimum angle: 0 degrees
Maximum angle: 180 degrees
```

These are logical limits. Confirm the actual safe mechanical range for the selected servo before enabling physical movement.

The agent must not be allowed to invent new action names or arbitrary GPIO operations.

Do not execute free-form code generated by an LLM.

---

## 10. ClawSense Deterministic Safety Supervisor

Implement the safety supervisor as a separate service/module with no dependency on the LLM.

Suggested interface:

```python
result = safety_supervisor.validate(
    proposal=proposal,
    system_state=current_state,
    context=current_context
)
```

The result must include:

- `decision_id`
- `proposal_id`
- `approved`
- `reason_code`
- `reason`
- `checks`
- `timestamp`

Example:

```json
{
  "approved": false,
  "reason_code": "ANGLE_OUT_OF_RANGE",
  "reason": "Servo angle exceeds configured maximum.",
  "checks": {
    "schema": "PASS",
    "allow_list": "PASS",
    "range": "FAIL",
    "system_state": "PASS"
  }
}
```

### Validation sequence

1. Parse and validate the schema.
2. Verify action allow-list membership.
3. Verify parameter types.
4. Verify numeric ranges.
5. Verify that sensor/context data is sufficiently fresh.
6. Verify the current system state.
7. Verify cooldown and rate limits.
8. Detect conflicting or duplicate commands.
9. Produce an explicit approval or rejection.
10. Persist the decision.
11. Dispatch only an approved action.
12. Record dispatch and device acknowledgement separately.

Validation must be deterministic for identical inputs and configuration.

Unknown or malformed commands must be rejected.

Missing safety-critical context must result in rejection or a predefined safe response.

Do not assume that a software approval proves physical safety. Firmware must enforce local limits independently.

### Audit integrity

Create append-oriented decision and event records.

Record who or what initiated an action, what was proposed, what checks ran, why it was approved/rejected, and whether execution was confirmed.

Do not claim cryptographic tamper-proof logging unless an actual cryptographic integrity mechanism has been implemented and tested.

---

## 11. State Machine

Implement explicit states and allowed transitions.

### States

`ONLINE_AGENT`

The agent service is available and can submit proposals for safety validation.

`DEGRADED`

The agent/network has a temporary failure or is approaching a timeout/retry limit. Local safety remains active.

`OFFLINE_LOCAL`

The agent cannot be relied upon. The ESP32 executes only predefined local rules.

`RECOVERY`

Connectivity has returned. Health checks and controlled re-entry are in progress.

`SAFE_LOCKDOWN`

A serious device fault, invalid safety configuration, or safety-critical failure prevents normal actuator commands.

### Example transitions

```text
ONLINE_AGENT
    |
    | Agent/network failure
    v
DEGRADED
    |
    | Failure persists beyond configured timeout
    v
OFFLINE_LOCAL
    |
    | Connectivity restored
    v
RECOVERY
    |
    | Health checks succeed
    v
ONLINE_AGENT
```

A critical safety fault may transition the system to `SAFE_LOCKDOWN` from any operational state.

Do not allow an automatic transition out of lockdown until the required fault checks and reset policy have been satisfied.

Implement:

- Explicit transition table.
- Transition reason codes.
- Timeout and retry policy.
- Recovery health checks.
- State transition audit events.
- Tests for allowed and forbidden transitions.

Use a monotonic clock for timeouts and cooldowns where appropriate.

---

## 12. Local Offline Fallback Controller

Implement a local rule-based controller that does not call the LLM.

It must operate using sensor readings, local configuration, and local state.

Requirements:

- No dependency on cloud services.
- No unrestricted actuator control.
- The same local safety limits apply.
- Invalid/stale sensor data is handled safely.
- Outputs have predefined safe states.
- No uncontrolled repeated actuator commands.
- Network recovery does not immediately grant unrestricted authority to the agent.

Provide at least two simple, documented local rules based on actual configured sensors.

The rules must be chosen after confirming the intended physical use case and the actual sensor modules.

Do not invent a safety-critical meaning for a sensor merely to satisfy the demo.

For example, if temperature exceeds a configured threshold, the local controller may raise an alert and move a lightweight, mechanically safe servo to a predefined position. The exact behavior must be documented and approved for the physical setup.

If the use case or sensor context does not justify a particular action, use a safe no-op, LED indication, or buzzer alert instead.

### Offline behavior

When the agent is unavailable:

1. Mark the agent as unavailable.
2. Transition through the configured failure state machine.
3. Reject new agent-originated actuator proposals when agent authority is disabled.
4. Continue sensor acquisition locally.
5. Run the local rule engine.
6. Validate its outputs using device-side safety rules.
7. Record the transition and local actions.
8. Restore agent authority only after recovery checks.

The local fallback must continue even if the backend process stops, provided the ESP32 remains powered and firmware is running.

---

## 13. Contextual Memory and Event Engine

Implement a bounded in-memory rolling buffer on the ESP32 where feasible.

The backend may maintain a persistent event history.

The event engine should:

- Read sensor values at configured intervals.
- Detect meaningful changes.
- Debounce noisy or repeated events.
- Attach timestamps or monotonic sequence numbers.
- Generate typed events.
- Retain only a bounded recent history on the device.
- Persist events on the backend when available.
- Continue local operation when backend storage is unavailable.

Example event types:

- `TEMPERATURE_UPDATED`
- `MOTION_DETECTED`
- `MOTION_CLEARED`
- `LIGHT_LEVEL_CHANGED` only if a light sensor is actually installed.
- A suitable event type for the confirmed replacement sensor.
- `AGENT_TIMEOUT`
- `ACTION_REJECTED`
- `FALLBACK_ACTIVATED`

The agent should receive a concise context summary instead of an unlimited raw event stream.

Do not send credentials or unnecessary personal data to the LLM.

---

## 14. ESP32-S3 Firmware Requirements

Organize firmware into independent modules:

- Sensor manager.
- Event engine.
- Context buffer.
- Safety supervisor.
- Local fallback controller.
- State machine.
- Actuator manager.
- Communication manager.
- OLED display manager.

### Firmware responsibilities

1. Initialize hardware safely.
2. Read and validate sensor data.
3. Maintain a local event buffer.
4. Monitor network/agent health where supported.
5. Maintain the local state machine.
6. Enforce actuator allow-list and limits.
7. Run offline rules when required.
8. Reject malformed or out-of-range commands.
9. Report telemetry and audit events when communication is available.
10. Update the OLED and status LEDs.
11. Recover from transient failures without entering unsafe loops.

### Firmware safety

- Initialize outputs to documented safe states.
- Validate incoming commands locally.
- Reject expired or duplicate commands.
- Do not trust the backend to be the only safety boundary.
- Do not block the sensor loop for long periods while waiting for an LLM.
- Use bounded network timeouts.
- Avoid repeated reboot loops.
- Preserve local operation when Wi-Fi is unavailable.
- Keep memory usage bounded.

### Physical output semantics

Suggested LED meanings:

- Green: online agent mode.
- Yellow: degraded or recovery.
- Red: offline local mode or safety fault; distinguish the exact reason on the OLED/dashboard.
- Buzzer: short, bounded alert for a safety rejection or fault.

Define the actual actuator safe state explicitly.

A safe state must be based on the physical setup, not assumed universally to be servo angle zero.

---

## 15. Communication and Command Acknowledgement

Use the simplest reliable protocol supported by the existing ESPClaw/firmware setup.

Possible approaches include HTTP REST or WebSockets, but select only after inspecting the existing firmware and libraries.

Document:

- Message format.
- Device identifier.
- Sequence or command ID.
- Timestamp/expiry.
- Request acknowledgement.
- Error handling.
- Retry policy.
- Device reconnect behavior.

An approved backend action is not equivalent to a successful device action.

Track these stages independently:

```text
PROPOSED
    |
    v
VALIDATED
    |
    v
APPROVED
    |
    v
DISPATCHED
    |
    v
ACKNOWLEDGED
    |
    v
STATE_CONFIRMED (if measurable)
```

Rejected actions must never be dispatched.

If the device does not acknowledge a command, mark it as a communication/execution uncertainty. Do not report it as successful.

Use command IDs and expiry checks to reduce duplicate or stale execution.

---

## 16. Database Design

Use SQLite for the initial implementation.

Create appropriate tables for:

### Devices

- Device ID.
- Device type.
- Firmware version.
- Last-seen timestamp.
- Connectivity status.

### Telemetry

- Record ID.
- Device ID.
- Sensor name.
- Numeric value or typed payload.
- Unit.
- Timestamp.
- Data quality.
- Real/simulated flag.

### Proposals

- Proposal ID.
- Source.
- Action name.
- Structured parameters.
- Explanation.
- Timestamp.
- Context reference.

### Safety decisions

- Decision ID.
- Proposal ID.
- Validation result.
- Reason code.
- Individual checks.
- Timestamp.

### Commands

- Command ID.
- Proposal/decision reference.
- Target device.
- Command status.
- Dispatch timestamp.
- Acknowledgement timestamp.
- Error information.

### Events

- Event ID.
- Device ID.
- Event category.
- Severity.
- Source.
- Structured details.
- Timestamp.
- Related proposal or command.
- Real/simulated flag.

### State transitions

- Previous state.
- New state.
- Reason code.
- Timestamp.
- Relevant diagnostic information.

Use indexes on timestamp, event category, device ID, and related IDs as appropriate.

Use migrations or a predictable initialization mechanism.

Persist safety decisions and command results independently so that an application restart does not silently erase the history.

---

## 17. Agent Integration

Define a small interface for agent providers.

For example:

```python
class AgentAdapter:
    async def propose_action(self, context):
        ...
```

Implement:

- A deterministic simulated agent.
- A verified adapter for the existing ESPClaw integration.

The simulator must produce structured proposals and support predictable test scenarios.

The actual integration must use the documented ESPClaw tool/action mechanism. Do not assume that an ESPClaw API exists merely because the name appears in the project title.

### Agent workflow

1. Receive a sensor/event context.
2. Build a bounded context summary.
3. Request a structured proposal.
4. Validate the proposal schema.
5. Submit the proposal to the deterministic safety supervisor.
6. Dispatch only if approved.
7. Wait for device acknowledgement.
8. Persist the entire trace.

The agent must not choose or override its own safety policy.

If the LLM returns malformed JSON, an unknown action, or an invalid parameter, reject the proposal.

If the agent times out, activate the configured state machine and local fallback.

Keep API keys on the backend or in the secure configuration mechanism supported by the device; never place them in the browser bundle.

---

## 18. Testing Requirements

Testing is mandatory. Do not claim completion merely because the application starts.

### Backend unit tests

Test:

- Valid action accepted.
- Angle of 250 degrees rejected.
- Negative angle rejected.
- Unknown action rejected.
- Malformed payload rejected.
- Wrong parameter type rejected.
- Missing parameters rejected.
- Invalid system state rejected.
- Stale context rejected.
- Cooldown enforced.
- Duplicate command handled safely.
- Database failure handled.
- Agent timeout handled.
- Forbidden state transition rejected.
- Local fallback operates without an agent.
- Reconnection follows recovery policy.

### API tests

Test:

- Health endpoint.
- Telemetry ingestion.
- Schema validation.
- Safety test endpoint.
- Event history.
- Event filters.
- WebSocket connection and updates.
- Device communication timeout.
- Error responses.
- Simulated/real data separation.

### Firmware tests

Where practical, unit-test pure validation and state-transition logic separately from hardware.

Then conduct physical tests for:

- Sensor reading.
- OLED update.
- LEDs.
- Buzzer.
- Servo movement if available.
- Invalid command rejection.
- Wi-Fi disconnection.
- Backend shutdown.
- Recovery after reconnection.

Document hardware tests that cannot be automated.

### Integration tests

Verify:

1. A valid proposal passes the backend safety supervisor.
2. The device independently checks the command.
3. A rejected proposal is not dispatched.
4. Device acknowledgement is recorded correctly.
5. An agent timeout activates fallback.
6. Backend failure does not disable local firmware safety.
7. Reconnection restores operation only after recovery checks.
8. Dashboard state reflects actual backend/device state.

### Test reporting

Provide:

- Automated test commands.
- Test results.
- Failed test explanations.
- Hardware test checklist.
- Known limitations.

Never fabricate successful test results.

---

## 19. Required Demo Scenarios

The project must support these scenarios.

### Scenario A: Normal operation

- Sensors produce actual readings.
- The context/event engine records a meaningful event.
- The agent proposes a valid action.
- The safety supervisor approves it.
- The ESP32 validates and executes the command.
- The dashboard shows the proposal, checks, acknowledgement, and event history.

If the agent is simulated, label the scenario accordingly.

### Scenario B: Unsafe action

Submit:

```json
{
  "action": "servo_move",
  "parameters": {
    "angle_degrees": 250
  }
}
```

Expected:

- Proposal is visible.
- Range validation fails.
- Safety result is `REJECTED`.
- Command dispatch is not attempted.
- Audit event is persisted.
- Red status indication or an appropriate safety alert is shown.

### Scenario C: Offline fallback

- Begin in online mode.
- Make the agent or network unavailable.
- Trigger the configured timeout.
- Transition to the local controller.
- Continue reading sensors.
- Execute only locally permitted actions.
- Record state changes and fallback events.

Demonstrate backend failure and device-local fallback separately if time allows. Losing cloud/agent access and losing the entire backend are different failure cases.

### Scenario D: Recovery

- Restore connectivity.
- Enter recovery mode.
- Perform health checks.
- Return to online agent mode only after checks pass.
- Record the transitions.

### Scenario E: Audit

Open an event and show:

- What triggered it.
- What the agent proposed.
- Which checks ran.
- Why the proposal was approved/rejected.
- Whether the device acknowledged execution.
- Which controller was active.

---

## 20. Implementation Milestones

Work in this order. At the end of each milestone, run the relevant tests and document the result.

### Milestone 1: Repository and specification

- Inspect the repository and hardware configuration.
- Record the actual ESPClaw version and integration method.
- Establish the repository structure.
- Create architecture and wiring documentation.
- Identify unresolved hardware assumptions.

**Exit criterion:** The implementation plan matches the existing project and does not depend on invented APIs or pins.

### Milestone 2: Backend safety core

- Implement action schemas.
- Implement deterministic safety validation.
- Implement state machine.
- Implement local fallback logic.
- Implement SQLite repositories.
- Write unit tests.

**Exit criterion:** Invalid actions are rejected and fallback logic can run without an LLM.

### Milestone 3: Frontend dashboard

- Build the dashboard layout.
- Implement all six pages.
- Connect API services.
- Add WebSocket updates.
- Implement loading/error/stale states.
- Clearly label simulation mode.

**Exit criterion:** All dashboard features work with the backend simulator, without fake real-hardware claims.

### Milestone 4: Firmware

- Verify pin configuration.
- Implement sensor acquisition.
- Implement event generation.
- Implement device-side safety.
- Implement local fallback.
- Implement state machine and status outputs.
- Implement communication and acknowledgements.

**Exit criterion:** The ESP32 can read the configured sensors, reject unsafe commands, and operate locally without the backend.

### Milestone 5: Integration

- Connect real telemetry.
- Connect the agent adapter.
- Connect validated commands.
- Implement acknowledgements.
- Persist audit events.
- Connect the dashboard to real status.

**Exit criterion:** At least one valid end-to-end hardware action works and at least one invalid action is rejected before execution.

### Milestone 6: Reliability

- Test Wi-Fi failure.
- Test agent timeout.
- Test backend failure.
- Test recovery.
- Test malformed messages.
- Test duplicate commands.
- Resolve power-related instability.
- Document limitations.

**Exit criterion:** Safety and fallback behavior is verified and documented.

### Milestone 7: Final review package

- Complete README.
- Complete architecture diagram.
- Complete wiring diagram.
- Complete API documentation.
- Complete safety policy documentation.
- Complete testing report.
- Prepare demo script.
- Capture genuine screenshots and test evidence.
- Verify a clean startup from documented commands.

**Exit criterion:** Another person can set up, run, test, and understand the project using the documentation.

---

## 21. Required Documentation

### README.md

Must include:

- Problem statement.
- Project objectives.
- Main contribution.
- Architecture.
- Technology stack.
- Hardware list.
- Software prerequisites.
- Setup commands.
- Environment variables.
- Firmware flashing procedure.
- How to start the application.
- Simulation versus hardware mode.
- Test commands.
- Troubleshooting.
- Known limitations.

### docs/architecture.md

Explain the data flow and the responsibilities of ESPClaw, the agent adapter, backend, safety supervisor, firmware, local fallback, database, and frontend.

### docs/wiring.md

Include actual verified GPIO assignments, voltage requirements, common-ground requirements, and connection diagrams. Mark unverified connections as unverified.

### docs/safety-model.md

Document allowed actions, ranges, state transitions, cooldowns, failure behavior, safe output state, and threat assumptions.

### docs/api-reference.md

Document endpoints, schemas, response codes, WebSocket messages, and example requests.

### docs/testing.md

Include test cases, commands, results, hardware verification, and known gaps.

### docs/demo-script.md

Provide a 3–5 minute demonstration script with exact actions, expected outputs, and fallback plans if Wi-Fi or the LLM fails.

### docs/limitations.md

Honestly document limitations such as the chosen LLM's availability, network dependency, hardware power constraints, sensor accuracy, and any unverified integration.

---

## 22. Final Review Rubric

Use this rubric as an internal quality checklist. It is not a guarantee of the professor's marking scheme.

| Area | Weight |
|---|---:|
| Working hardware and end-to-end integration | 20 |
| Deterministic safety supervisor | 20 |
| Offline fallback and state machine | 15 |
| AI/context integration and decision trace | 10 |
| Dashboard quality and usability | 10 |
| Testing and reliability evidence | 10 |
| Architecture and documentation | 10 |
| Demonstration clarity | 5 |
| **Total** | **100** |

The agent must produce an honest self-assessment against these categories and list any unimplemented requirements.

Do not claim a category is complete without evidence.

A beautiful dashboard cannot compensate for a safety supervisor that does not actually validate commands. Likewise, a simulated demo cannot be described as a fully integrated hardware system.

---

## 23. Definition of Done

The project is complete only when the following are satisfied:

- [ ] Dashboard starts using documented commands.
- [ ] Backend starts using documented commands.
- [ ] SQLite stores telemetry and audit history.
- [ ] Actual sensor readings are visible when hardware mode is enabled.
- [ ] Unconfigured sensors are shown as unavailable, not fabricated.
- [ ] AI proposals use a structured action contract.
- [ ] Deterministic validation is independent of the LLM.
- [ ] Invalid commands are rejected before dispatch.
- [ ] Firmware independently validates actuator commands.
- [ ] Local fallback continues without the LLM.
- [ ] State transitions are explicit and tested.
- [ ] Dashboard displays real device/backend status.
- [ ] Simulated and real data are clearly distinguished.
- [ ] Device acknowledgement is distinguished from command approval.
- [ ] Events and safety decisions are persisted.
- [ ] Automated tests are included and executed.
- [ ] Hardware test results are documented.
- [ ] The final demo can show normal, rejected, offline, and recovery scenarios.
- [ ] README, wiring, architecture, safety, and testing documentation are complete.
- [ ] No secrets are committed.
- [ ] Known limitations are disclosed.

---

## 24. Final Instructions to the Coding Agent

Build the project in milestones rather than generating the entire codebase in one unverified pass.

For each milestone:

1. Inspect existing code and requirements.
2. Implement the smallest complete working increment.
3. Run relevant tests and report actual results.
4. Fix errors before proceeding.
5. Update documentation.
6. Identify any hardware or integration requirement that needs human verification.

Do not silently replace real functionality with mock data.

Do not claim that a device, LLM, or external service is connected unless the connection has been verified.

Do not bypass safety validation to make the demo appear successful.

Do not rewrite working project components unnecessarily.

If a required integration is blocked, explain the blocker, implement a clearly labelled adapter/simulator, and preserve the intended production integration point.

**Final priority: a working, explainable, independently validated AI-IoT control system with verified local fallback—not merely an attractive dashboard.**
