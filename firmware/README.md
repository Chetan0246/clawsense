# ClawSense ESP32-S3 Firmware

Firmware for the ClawSense context-aware agentic IoT node. It samples sensors,
maintains a bounded event/context memory, enforces a **deterministic on-device
safety supervisor**, runs a **local fallback controller** when the agent/network
is unavailable, drives actuators through a single hardware-abstraction module,
and exposes the HTTP contract the backend expects.

> **Hardware status:** no board has been flashed or physically verified yet.
> Pin assignments below are chosen to avoid ESP32-S3 strapping/USB/flash pins
> and to keep all analog inputs on ADC1, but they are **unverified until a
> bench check is performed** (see `docs/wiring.md` at the repo root).

---

## 1. Build & flash

Requires [PlatformIO](https://platformio.org/) (`pio`).

```bash
cd firmware

# Build
pio run

# Flash over USB
pio run -t upload

# Serial monitor (115200 baud)
pio device monitor
```

The environment is `[env:esp32-s3-devkitc-1]` (see `platformio.ini`):
`platform = espressif32`, `board = esp32-s3-devkitc-1`, `framework = arduino`.

Libraries (auto-installed by PlatformIO): `ESP32Servo`, `DHT sensor library`
(+ `Adafruit Unified Sensor`), `Adafruit SSD1306`, `Adafruit GFX Library`,
`ArduinoJson` (v7).

---

## 2. WiFi configuration (secrets are never committed)

```bash
cp include/secrets.example.h include/secrets.h
$EDITOR include/secrets.h      # fill in WIFI_SSID / WIFI_PASSWORD
```

* `include/secrets.h` is git-ignored and **must never be committed**.
* `config.h` includes it only when present (`__has_include`).
* **With no `secrets.h`** the firmware builds and runs **AP-less / local-only**:
  WiFi is disabled, the HTTP server does not start, and the node operates in
  `OFFLINE_LOCAL` using the local fallback controller. This is a supported mode,
  not an error.
* Credentials are never printed in logs — only the assigned IP address is.

---

## 3. Wiring table

Board: **ESP32-S3-DevKitC-1**. All analog inputs are on **ADC1** (GPIO1–GPIO10)
because ADC2 is unusable while WiFi is active.

| Signal                | GPIO | Dir    | Notes / rationale                                   |
|-----------------------|:----:|:------:|-----------------------------------------------------|
| DHT22 data (digital)  | 16   | bidir  | DHT22 1-Wire data; needs a pull-up (module has one) |
| Temp analog (fallback)| 1    | in     | ADC1_CH0 — TMP36 / LM35 (analog source only)        |
| Humidity analog (fallb)| 2   | in     | ADC1_CH1 — analog humidity module (analog only)     |
| Light / LDR analog    | 4    | in     | ADC1_CH3 — third-sensor slot (only if LIGHT)        |
| PIR motion (digital)  | 5    | in     | HIGH = motion                                       |
| Servo PWM             | 6    | out    | 50 Hz via ESP32Servo (500–2400 µs)                  |
| Buzzer (PWM/LEDC)     | 7    | out    | `tone()`/`noTone()` (LEDC-backed square wave)       |
| OLED SDA (I2C)        | 8    | bidir  | SSD1306 @ 0x3C                                      |
| OLED SCL (I2C)        | 9    | out    | SSD1306 @ 0x3C                                      |
| Status LED — GREEN    | 11   | out    | discrete LED, active HIGH                           |
| Status LED — YELLOW   | 12   | out    | discrete LED, active HIGH                           |
| Status LED — RED      | 13   | out    | discrete LED, active HIGH                           |
| Button 1 (active LOW) | 14   | in     | `INPUT_PULLUP`; acknowledge local alert             |
| Button 2 (active LOW) | 15   | in     | `INPUT_PULLUP`; request sensor re-read              |

**Temperature / humidity source.** By default the node uses the **DHT22**
(`CONFIG_TEMP_HUMIDITY_SOURCE_DHT22`). An analog fallback path
(TMP36/LM35 + analog humidity module on GPIO1/GPIO2) can be selected in
`config.h` via `CONFIG_TEMP_HUMIDITY_SOURCE = CONFIG_TEMP_HUMIDITY_SOURCE_ANALOG`.
The DHT22 data line (GPIO16) and the analog temperature input (GPIO1) are
separate pins, so the DHT pull-up can never fight an analog divider; only one
source is active at a time.

**Third sensor.** The original design assumed an LDR. The actual third sensor is
not yet confirmed, so the slot defaults to `CONFIG_THIRD_SENSOR_KIND =
CONFIG_THIRD_SENSOR_NONE` and `light_lux` is reported **NOT_CONFIGURED** with
`value: null`. Set the slot to `CONFIG_THIRD_SENSOR_LIGHT` to enable the LDR
path on GPIO4. A reading is never fabricated.

**Status LEDs.** Three discrete active-HIGH LEDs are driven one at a time:
green = `ONLINE_AGENT`, yellow = `DEGRADED`/`RECOVERY`, red =
`OFFLINE_LOCAL`/`SAFE_LOCKDOWN` or fault (PLAN.md 14). An explicit
`set_status_led` action may override the state colour until the next transition.

**Buttons.** Active-LOW to GND with internal pull-ups, debounced for ≥ 30 ms.
They produce **local, non-actuator effects only**: button 1 records an operator
acknowledgement, button 2 requests an immediate sensor re-read. Neither drives
the servo/buzzer/LEDs nor bypasses the safety supervisor.

**Pins deliberately avoided:** strapping pins GPIO0/3/45/46 (boot sensitivity),
native-USB GPIO19/20, SPI-flash GPIO26–32 and octal-PSRAM GPIO33–37, and the
input-only GPIO46. See the table comment in `include/config.h`.

### Power

* The **servo must be powered from a separate 5 V supply with a common ground**
  shared with the ESP32. Never power a servo from a GPIO or the 3V3 rail.
* If the servo causes resets, USB instability or WiFi drops, disconnect it and
  use the LEDs + buzzer as the actuator demonstration (PLAN.md 3).
* Sensors and the OLED are 3V3-compatible; do not feed 5 V logic into GPIOs.

---

## 4. HTTP contract

The node serves these endpoints (port 80) and matches
`backend/app/transports/http_transport.py` exactly.

### `GET /health`

```json
{"status":"ok","firmware":"0.1.0","device_id":"esp32s3-clawsense-01",
 "state":"ONLINE_AGENT","controller":"agent","uptime_ms":12345}
```

### `GET /telemetry`

```json
{
  "device_id": "esp32s3-clawsense-01",
  "timestamp": 1700000000000,
  "simulated": false,
  "readings": {
    "temperature_c":   {"value": 24.5, "unit": "C",   "status": "OK"},
    "humidity_percent":{"value": 61.0, "unit": "%",   "status": "OK"},
    "motion":          {"value": true, "unit": "bool","status": "OK"},
    "light_lux":       {"value": null, "unit": "lux", "status": "NOT_CONFIGURED"}
  }
}
```

* `status` is one of `OK | STALE | ERROR | NOT_CONFIGURED | UNAVAILABLE`.
* A missing/failed reading is reported with `"value": null` — it is **never
  coerced to 0**. `light_lux` stays `NOT_CONFIGURED` until the third-sensor slot
  is configured (`CONFIG_THIRD_SENSOR_KIND = CONFIG_THIRD_SENSOR_LIGHT`).
* A failed DHT22 read is reported `ERROR` with `value: null`; the last good
  reading is reused between the ≥ 2000 ms DHT22 samples and becomes `STALE`
  only if it ages beyond `SENSOR_STALE_MS`.
* `timestamp` is epoch milliseconds when NTP is synced; otherwise it falls back
  to monotonic `millis()` (no RTC on the board) — a documented limitation.

### `POST /command`

Request (the backend sends `action` + `parameters`; `command_id` is optional and
echoed back when present):

```json
{"command_id":"abc-123","action":"servo_move","parameters":{"angle_degrees":90}}
```

Approved response:

```json
{"acknowledged":true,"state_confirmed":true,
 "detail":"Command executed and state confirmed.","reason_code":"APPROVED",
 "command_id":"abc-123",
 "reported_state":{"servo_angle":90,"servo_target":90,"servo_moving":false,
                   "buzzer_active":false,"led":"off",
                   "state":"ONLINE_AGENT","controller":"agent"}}
```

Rejected response (structured `200`, so the backend records the rejection rather
than a transport error):

```json
{"acknowledged":false,"state_confirmed":false,
 "detail":"Servo angle 250 outside allowed 0-180 degrees.",
 "reason_code":"ANGLE_OUT_OF_RANGE","reported_state":{}}
```

`reason_code` values mirror the backend safety supervisor:
`APPROVED, SCHEMA_INVALID, UNKNOWN_ACTION, INVALID_PARAMETERS,
ANGLE_OUT_OF_RANGE, DURATION_OUT_OF_RANGE, CONTEXT_MISSING, CONTEXT_STALE,
INVALID_SYSTEM_STATE, COOLDOWN_ACTIVE, DUPLICATE_COMMAND`.

---

## 5. State machine

`ONLINE_AGENT → DEGRADED → OFFLINE_LOCAL → RECOVERY → ONLINE_AGENT`, plus
`SAFE_LOCKDOWN` reachable from any operational state.

| Timeout | Value | Source |
|---|---|---|
| Degraded after | 15 s | `DEGRADED_TIMEOUT_MS` |
| Offline-local after | 45 s | `OFFLINE_TIMEOUT_MS` |
| Recovery confirmation | 3 checks over ≥ 5 s | `RECOVERY_HEALTH_CHECKS` / `RECOVERY_CONFIRM_MS` |

Illegal transitions are **refused**, not coerced. Lockdown is exited only via an
explicit reset (`clearLockdown()`), and recovery always re-enters through
`RECOVERY`.

---

## 6. Safety notes

* **Deterministic, independent validation.** Every command is re-validated
  on-device (`safety_supervisor.cpp`) regardless of any backend approval. A
  software approval is not proof of physical safety.
* **Fail closed.** Malformed JSON, unknown actions, wrong parameter types,
  out-of-range values, invalid LED colours, missing/stale context, disallowed
  source-in-state, cooldowns and duplicates are all rejected before any actuator
  moves.
* **Local fallback is independent of the LLM/network** and its outputs are
  validated by the same supervisor as backend commands.
* **Limits are centralised** in `include/config.h` and must be kept in sync with
  `backend/app/config.py` (`Settings`). Compile-time `static_assert`s reject a
  nonsensical safety configuration.
* **Separate servo supply + common ground** is mandatory.
* **Servo holds position on comms loss.** The documented safe state is *buzzer
  off, LED off, servo stays put* — it is never forced to a position that could
  damage the mechanism.
* **The display is never safety-critical.** If the OLED is absent the firmware
  logs it once and continues.
* **No secrets in logs.** WiFi credentials are never printed.

---

## 7. Source layout

```
firmware/
├── platformio.ini
├── include/
│   ├── config.h            # pins, limits, feature flags (single source of truth)
│   ├── secrets.example.h   # WiFi template (copy to secrets.h — git-ignored)
│   ├── action.h            # Action struct, name/colour maps, JSON parse
│   ├── sensor_manager.h
│   ├── event_engine.h
│   ├── context_buffer.h
│   ├── safety_supervisor.h
│   ├── local_controller.h
│   ├── state_machine.h
│   ├── actuator_manager.h
│   ├── buttons.h              # debounced active-LOW push buttons (non-actuator)
│   ├── communication.h
│   └── display.h
└── src/
    ├── main.cpp                 # setup()/loop(), non-blocking scheduler
    ├── sensor_manager.cpp       # DHT22 (+ analog fallback), PIR, third slot
    ├── event_engine.cpp
    ├── context_buffer.cpp
    ├── safety_supervisor.cpp
    ├── local_controller.cpp
    ├── state_machine.cpp
    ├── actuator_manager.cpp
    ├── buttons.cpp
    ├── communication.cpp
    └── display.cpp
```
