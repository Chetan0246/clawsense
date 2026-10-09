# Wiring and hardware

This document describes how to connect the ESP32-S3 sensor/actuator node. Pin
assignments are defined once in [`firmware/include/config.h`](../firmware/include/config.h).

> **Read the safety notes before powering anything.** The servo must not be
> powered from the ESP32's 3.3 V regulator.

## Verification status — ⚠️ UNVERIFIED

**No physical hardware was available when this document was written.** Every pin
assignment, voltage assumption, and sensor conversion below is a *proposed*
configuration, not a verified one. PLAN.md section 3 requires the exact third
sensor model, ESP32-S3 pinout, OLED controller, servo availability, and
board-specific wiring to be verified before finalizing firmware.

Before connecting anything, verify:

- [ ] The exact ESP32-S3 board variant and its available GPIOs (some boards expose
      fewer pins, and octal-PSRAM variants reserve more).
- [ ] The third sensor model, its supply voltage, and its output type.
- [ ] The OLED controller (SSD1306 vs SH1106) and its I²C address.
- [ ] The servo's rated supply voltage and stall current.
- [ ] That every proposed GPIO is free on your board (no conflicting onboard use).
- [ ] DHT22 supply voltage and pull-up resistor (the DHT22 needs a 4.7–10 kΩ
      pull-up on the data line).

Treat everything in this file as **unverified** until each box is ticked.

## Bill of materials

| Item | Example | Notes |
| --- | --- | --- |
| MCU board | ESP32-S3-DevKitC-1 | Arduino framework via PlatformIO |
| Temperature + humidity | **DHT22** (digital) | needs a 4.7–10 kΩ pull-up on the data line |
| Motion sensor | HC-SR501 PIR (digital) | 3.3 V-tolerant output preferred |
| Third sensor | *(not yet chosen)* | configurable slot; reports `NOT_CONFIGURED` until set |
| Actuator | hobby servo (SG90/MG996R) | **separate 5 V supply** |
| Alert | piezo buzzer | via transistor if current > GPIO limit |
| Status LEDs | 3 × discrete LED (green, yellow, red) | active HIGH, one at a time |
| Push buttons | 2 × momentary | active LOW, internal pull-up |
| Display | SSD1306 OLED 128×64, I²C, 0x3C | optional |
| Power | 5 V supply for servo, 3.3 V for logic | **common ground required** |

Optional analog fallback (only if the DHT22 is unavailable): a TMP36/LM35
temperature sensor and an analog humidity module, selected via
`CONFIG_TEMP_HUMIDITY_SOURCE = ANALOG`. Do not populate both sources on GPIO1.

## Pin assignment

Board: **ESP32-S3-DevKitC-1**

| Signal | GPIO | Direction | Notes |
| --- | --- | --- | --- |
| DHT22 data | **1** | bidirectional | 1-Wire data; **requires a 4.7–10 kΩ pull-up to 3.3 V** |
| Temperature analog (ADC1_CH0) | **1** | input | analog fallback only (TMP36/LM35); shared with DHT22 |
| Humidity analog (ADC1_CH1) | **2** | input | analog fallback only |
| Third-sensor analog (ADC1_CH3) | **4** | input | third-sensor slot (only when configured as LIGHT) |
| PIR motion | **5** | input | digital HIGH = motion |
| Servo PWM | **6** | output | 50 Hz servo PWM |
| Buzzer | **7** | output | tone / LEDC square wave |
| OLED SDA (I²C) | **8** | bidirectional | address `0x3C` |
| OLED SCL (I²C) | **9** | output | I²C clock |
| Status LED — Green | **11** | output | active HIGH |
| Status LED — Yellow | **12** | output | active HIGH |
| Status LED — Red | **13** | output | active HIGH |
| Button 1 | **14** | input | `INPUT_PULLUP`, active LOW — acknowledge local alert |
| Button 2 | **15** | input | `INPUT_PULLUP`, active LOW — request sensor re-read |

### Why these pins

- **ADC1 only for analog inputs.** ADC2 (GPIO11–GPIO20) is unusable while Wi-Fi
  is active. Any analog input therefore sits on ADC1 (GPIO1–GPIO10).
- **Strapping pins avoided.** GPIO0, GPIO3, GPIO45 and GPIO46 are left free so
  boot mode is not affected by external circuitry.
- **Native USB pins avoided.** GPIO19/GPIO20 are left free for serial/JTAG.
- **Flash/PSRAM pins avoided.** GPIO26–GPIO37 are not used.
- **GPIO46 is input-only** and is not used as an output.

### GPIO1 is shared by design

The DHT22 data line and the analog temperature fallback both use GPIO1. Only one
temperature/humidity source is active at a time (`CONFIG_TEMP_HUMIDITY_SOURCE`),
so the pin is never driven by both. If you populate **both** the DHT22 and the
analog temperature sensor, their pull-up/divider networks will fight — populate
only one.

### Status LED semantics

Three **discrete** LEDs, driven one at a time (PLAN.md section 14):

| State | LED |
| --- | --- |
| `ONLINE_AGENT` | Green |
| `DEGRADED`, `RECOVERY` | Yellow |
| `OFFLINE_LOCAL`, `SAFE_LOCKDOWN`, fault | Red |

### Buttons

Both buttons are active-LOW with the internal pull-up enabled and are debounced
(≥ 30 ms) in firmware. They perform **local, non-actuator** actions only:

| Button | Action |
| --- | --- |
| 1 | Acknowledge / clear a local alert |
| 2 | Request an immediate sensor re-read |

**A button must never drive an actuator directly.** All actuator actions still
pass through the on-device safety supervisor.

## Power and grounding (critical)

```
   5V supply ──┬───────────────► Servo VCC
               │
               └──(never feed 5V into ESP32 3.3V or a GPIO)──►

   ESP32 3V3  ────────────────► Sensor VCC (3.3V sensors)
   ESP32 GND  ────┬───────────► Sensor GND
                  ├───────────► Servo GND   ← COMMON GROUND (mandatory)
                  └───────────► 5V supply GND
```

- The servo draws current spikes that will brown out the ESP32 if it is powered
  from the board's regulator. **Always use a separate 5 V supply.**
- A **common ground** between the ESP32, the sensors, and the servo supply is
  mandatory; without it the PWM signal has no reference and the servo will jitter
  or fail.
- Add a large bulk capacitor (≥470 µF) across the servo supply if you see resets.
- If the buzzer draws more than a GPIO can source, drive it through a transistor.

## I²C display

- SDA → GPIO8, SCL → GPIO9, VCC → 3.3 V, GND → GND.
- The firmware degrades gracefully if the display is absent.

## Safe state on communication loss

Documented and implemented behaviour:

| Output | Behaviour on comms loss |
| --- | --- |
| Buzzer | **OFF** |
| Status LED | **OFF** (or driven by the local fallback rule) |
| Servo | **HOLDS its last position** — it is never forced to a new position, and never left actively driving against a mechanical stop |

This is a deliberate choice: moving a servo to an unknown "safe" position can
itself cause damage. Holding position plus the local fallback rules is the
documented safe state.

## Calibration

- **DHT22 (default):** factory-calibrated; no conversion constants needed. The
  DHT22 needs ≥ 2 s between reads, which the firmware respects.
- **Analog fallback** (only when `CONFIG_TEMP_HUMIDITY_SOURCE = ANALOG`):
  - `CONFIG_TEMP_SENSOR_TYPE` — set to `CONFIG_TEMP_SENSOR_TMP36` or `..._LM35`.
  - `CONFIG_HUMIDITY_MV_AT_0_PCT` / `CONFIG_HUMIDITY_MV_AT_100_PCT` — measure the
    module's output at known humidity.
- **Third sensor (LIGHT):** `CONFIG_LIGHT_LUX_PER_MV` — rough linearisation, for
  relative change detection only.

Uncalibrated analog values still exercise the full pipeline, but do not treat
them as accurate measurements.

## Safety limits must match the backend

The following firmware constants mirror backend settings and must be kept in
sync. If they ever disagree, the **more restrictive** value must win.

| Firmware (`config.h`) | Backend (`Settings`) |
| --- | --- |
| `SERVO_MIN_DEGREES` / `SERVO_MAX_DEGREES` | `servo_min_degrees` / `servo_max_degrees` |
| `BUZZER_MAX_MS` | `buzzer_max_ms` |
| `TEMP_HIGH_C` / `TEMP_LOW_C` / `HUMIDITY_HIGH_PERCENT` | `temp_high_c` / `temp_low_c` / `humidity_high_percent` |
| `ACTION_COOLDOWN_MS` | `action_cooldown_seconds` |
| `CONTEXT_MAX_AGE_MS` | `context_max_age_seconds` |
| `DEGRADED_TIMEOUT_MS` / `OFFLINE_TIMEOUT_MS` | `degraded_timeout_seconds` / `offline_timeout_seconds` |
