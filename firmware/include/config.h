#pragma once

// ===========================================================================
// ClawSense firmware — central configuration (PLAN.md sections 4, 20, 21).
//
// This file is the SINGLE place where pin assignments, limits, intervals and
// feature flags live.  Nothing else in the firmware should hard-code a pin or
// a safety limit.
//
// SAFETY: every value under "Safety limits" MUST be kept in sync with the
// backend settings in backend/app/config.py (class Settings).  The backend and
// the firmware are independent safety boundaries; if they disagree the more
// restrictive value must win.  A comment on each block names the backend field.
// ===========================================================================

#include <Arduino.h>

// ---------------------------------------------------------------------------
// Optional WiFi secrets.
//
// `secrets.h` is NOT committed (see .gitignore).  When it is absent we fall
// back to empty credentials and the node runs AP-less / local-only, which is a
// valid and safe operating mode (OFFLINE_LOCAL).
// ---------------------------------------------------------------------------
#if __has_include("secrets.h")
#include "secrets.h"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif
#ifndef WIFI_HOSTNAME
#define WIFI_HOSTNAME "clawsense-esp32"
#endif

// ---------------------------------------------------------------------------
// Device identity (must match CLAWSENSE_DEVICE_ID on the backend).
// ---------------------------------------------------------------------------
constexpr char DEVICE_ID[]        = "esp32s3-clawsense-01";
constexpr char DEVICE_TYPE[]      = "esp32s3";
constexpr char FIRMWARE_VERSION[] = "0.1.0";

// ---------------------------------------------------------------------------
// Compile-time logging.
//
// Levels: 0=off 1=error 2=warn 3=info 4=debug.  Logs NEVER print secrets or
// WiFi credentials.
// ---------------------------------------------------------------------------
#ifndef CONFIG_LOG_LEVEL
#define CONFIG_LOG_LEVEL 3
#endif

#if CONFIG_LOG_LEVEL >= 1
#define CS_LOGE(fmt, ...) do { Serial.printf("[E][%8lu] " fmt "\n", (unsigned long)millis(), ##__VA_ARGS__); } while (0)
#else
#define CS_LOGE(fmt, ...) do {} while (0)
#endif
#if CONFIG_LOG_LEVEL >= 2
#define CS_LOGW(fmt, ...) do { Serial.printf("[W][%8lu] " fmt "\n", (unsigned long)millis(), ##__VA_ARGS__); } while (0)
#else
#define CS_LOGW(fmt, ...) do {} while (0)
#endif
#if CONFIG_LOG_LEVEL >= 3
#define CS_LOGI(fmt, ...) do { Serial.printf("[I][%8lu] " fmt "\n", (unsigned long)millis(), ##__VA_ARGS__); } while (0)
#else
#define CS_LOGI(fmt, ...) do {} while (0)
#endif
#if CONFIG_LOG_LEVEL >= 4
#define CS_LOGD(fmt, ...) do { Serial.printf("[D][%8lu] " fmt "\n", (unsigned long)millis(), ##__VA_ARGS__); } while (0)
#else
#define CS_LOGD(fmt, ...) do {} while (0)
#endif

// ===========================================================================
// FEATURE FLAGS
//
// A sensor that is not physically installed must be reported NOT_CONFIGURED,
// never fabricated (PLAN.md 2.2 / 3).  Disable a flag to do exactly that.
// ===========================================================================
#define CONFIG_ENABLE_TEMPERATURE 1
#define CONFIG_ENABLE_HUMIDITY    1
#define CONFIG_ENABLE_MOTION      1
#define CONFIG_ENABLE_BUTTONS     1

// The original design assumed the third sensor was an LDR.  The actual third
// sensor is NOT yet confirmed, so the slot defaults to NONE and is reported
// NOT_CONFIGURED — a reading is never fabricated (PLAN.md 2.2 / 3 / 23).
//   CONFIG_THIRD_SENSOR_NONE  : no third sensor -> light_lux NOT_CONFIGURED
//   CONFIG_THIRD_SENSOR_LIGHT : LDR in a divider -> light_lux OK
#define CONFIG_THIRD_SENSOR_NONE   0
#define CONFIG_THIRD_SENSOR_LIGHT  1
#define CONFIG_THIRD_SENSOR_KIND   CONFIG_THIRD_SENSOR_NONE

// light_lux is only exposed when the slot really is a light sensor.  This is
// derived so there is a single source of truth; it stays a preprocessor macro
// (never `#if` on a `constexpr`).
#define CONFIG_ENABLE_LIGHT (CONFIG_THIRD_SENSOR_KIND == CONFIG_THIRD_SENSOR_LIGHT)

#define CONFIG_ENABLE_SERVO       1
#define CONFIG_ENABLE_BUZZER      1
#define CONFIG_ENABLE_STATUS_LED  1
#define CONFIG_ENABLE_DISPLAY     1

// ===========================================================================
// PIN ASSIGNMENT  (PLAN.md 4 / 20)
//
// Board: ESP32-S3-DevKitC-1.
//
// ESP32-S3 pin constraints honoured below:
//   * ADC1 = GPIO1..GPIO10.  ADC2 (GPIO11..GPIO20) is UNUSABLE while WiFi is
//     active, so every analog input MUST be on ADC1.  -> temp/humidity/light
//     all use ADC1 pins.
//   * Strapping pins GPIO0, GPIO3, GPIO45, GPIO46 are avoided entirely
//     (booting is sensitive to their level at reset).
//   * Native-USB pins GPIO19 (D-) / GPIO20 (D+) are avoided so serial/JTAG
//     stays available.
//   * SPI flash pins GPIO26..GPIO32 and (on octal-PSRAM modules) GPIO33..GPIO37
//     are avoided.
//   * GPIO46 is input-only and is not used.
//
// Signal                GPIO   Direction  Notes / rationale
// --------------------  -----  ---------  ------------------------------------
// DHT22 data (digital)  16     bidir      DHT22 1-Wire data; needs a pull-up
// TEMP analog (ADC1)    1      input      ADC1_CH0; analog fallback (TMP36/LM35)
// HUMID analog (ADC1)   2      input      ADC1_CH1; analog fallback
// LIGHT analog (ADC1)   4      input      ADC1_CH3; third-sensor slot (if LIGHT)
// PIR motion (digital)  5      input      digital high = motion
// SERVO PWM             6      output     ESP32Servo 50 Hz PWM
// BUZZER (PWM/LEDC)     7      output     tone()/LEDC square wave
// OLED SDA (I2C)        8      bidir      I2C data (address 0x3C)
// OLED SCL (I2C)        9      output     I2C clock
// STATUS LED GREEN      11     output     discrete LED, active HIGH
// STATUS LED YELLOW     12     output     discrete LED, active HIGH
// STATUS LED RED        13     output     discrete LED, active HIGH
// BUTTON 1 (active LOW) 14     input      INPUT_PULLUP; acknowledge local alert
// BUTTON 2 (active LOW) 15     input      INPUT_PULLUP; request sensor re-read
//
// The DHT22 (GPIO16) and the analog temperature fallback (GPIO1) use SEPARATE
// pins, so the DHT pull-up can never fight an analog divider.  Only ONE
// temperature/humidity source is active at a time (see
// CONFIG_TEMP_HUMIDITY_SOURCE below).  Any analog input stays on ADC1 (ADC2 is
// unusable while WiFi is on).
//
// The status indication is three DISCRETE LEDs (active HIGH), driven one at a
// time: green = ONLINE_AGENT, yellow = DEGRADED/RECOVERY, red =
// OFFLINE_LOCAL/SAFE_LOCKDOWN or fault (PLAN.md 14).
// ===========================================================================
constexpr int CONFIG_PIN_DHT_DATA    = 16;
constexpr int CONFIG_PIN_TEMP_ADC    = 1;   // analog fallback only
constexpr int CONFIG_PIN_HUMID_ADC   = 2;   // analog fallback only
constexpr int CONFIG_PIN_LIGHT_ADC   = 4;   // third-sensor slot (if LIGHT)
constexpr int CONFIG_PIN_PIR         = 5;
constexpr int CONFIG_PIN_SERVO       = 6;
constexpr int CONFIG_PIN_BUZZER      = 7;
constexpr int CONFIG_PIN_I2C_SDA     = 8;
constexpr int CONFIG_PIN_I2C_SCL     = 9;
constexpr int CONFIG_PIN_LED_GREEN   = 11;
constexpr int CONFIG_PIN_LED_YELLOW  = 12;
constexpr int CONFIG_PIN_LED_RED     = 13;
constexpr int CONFIG_PIN_BUTTON_1    = 14;
constexpr int CONFIG_PIN_BUTTON_2    = 15;

// OLED geometry / address.
constexpr int    CONFIG_OLED_WIDTH   = 128;
constexpr int    CONFIG_OLED_HEIGHT  = 64;
constexpr uint8_t CONFIG_OLED_ADDR   = 0x3C;

// ===========================================================================
// SAFETY LIMITS  (backend: Settings.servo_min_degrees / servo_max_degrees /
// buzzer_max_ms / allowed_actions / LedColor)
//
// These are LOGICAL limits.  Confirm the real mechanical range of the servo
// before enabling physical movement.
// ===========================================================================
constexpr int SERVO_MIN_DEGREES = 0;      // Settings.servo_min_degrees
constexpr int SERVO_MAX_DEGREES = 180;    // Settings.servo_max_degrees
constexpr int BUZZER_MIN_MS     = 1;      // backend enforces 1..buzzer_max_ms
constexpr int BUZZER_MAX_MS     = 2000;   // Settings.buzzer_max_ms

// A nonsensical safety configuration must fail at COMPILE time, not runtime.
static_assert(SERVO_MIN_DEGREES < SERVO_MAX_DEGREES,
              "servo min must be less than servo max");
static_assert(BUZZER_MIN_MS >= 1 && BUZZER_MIN_MS < BUZZER_MAX_MS,
              "buzzer duration window must be 1..BUZZER_MAX_MS");
static_assert(SERVO_MIN_DEGREES >= 0 && SERVO_MAX_DEGREES <= 180,
              "servo limits must stay within the logical 0..180 range");

// Local fallback thresholds (backend: Settings.temp_high_c / temp_low_c /
// humidity_high_percent).  fallback_controller.py uses the same rules.
constexpr float TEMP_HIGH_C           = 35.0f;  // Settings.temp_high_c
constexpr float TEMP_LOW_C            = 5.0f;   // Settings.temp_low_c
constexpr float HUMIDITY_HIGH_PERCENT = 80.0f;  // Settings.humidity_high_percent
constexpr int   FALLBACK_OBSERVATION_ANGLE = 45; // fallback_controller.py R4

static_assert(TEMP_LOW_C < TEMP_HIGH_C,
              "low-temperature threshold must be below high-temperature threshold");
static_assert(FALLBACK_OBSERVATION_ANGLE >= SERVO_MIN_DEGREES &&
                  FALLBACK_OBSERVATION_ANGLE <= SERVO_MAX_DEGREES,
              "fallback observation angle must lie within the servo range");

// The local controller re-issues its current rule periodically so a lost
// actuator state self-heals, but not so often that it floods the bus.
constexpr unsigned long LOCAL_REISSUE_MS = 10000UL;

// Audible alert duration used by the high-temperature fallback rule.
constexpr int FALLBACK_ALERT_BEEP_MS = 500;

// Timing policy (backend: Settings.context_max_age_seconds /
// action_cooldown_seconds / degraded_timeout_seconds / offline_timeout_seconds).
constexpr unsigned long CONTEXT_MAX_AGE_MS   = 30000UL;  // 30 s
constexpr unsigned long ACTION_COOLDOWN_MS   = 3000UL;   // 3 s
constexpr unsigned long DEGRADED_TIMEOUT_MS  = 15000UL;  // 15 s
constexpr unsigned long OFFLINE_TIMEOUT_MS   = 45000UL;  // 45 s

// Recovery policy: require N consecutive successful health checks spread over
// at least RECOVERY_CONFIRM_MS before returning to ONLINE_AGENT.  Agent
// authority is never restored instantly (PLAN.md 12).
constexpr int           RECOVERY_HEALTH_CHECKS = 3;
constexpr unsigned long RECOVERY_CONFIRM_MS    = 5000UL;

// ===========================================================================
// SCHEDULING INTERVALS (all millis()-based; loop() never blocks)
// ===========================================================================
constexpr unsigned long SENSOR_SAMPLE_INTERVAL_MS = 1000UL;
constexpr unsigned long EVENT_EVAL_INTERVAL_MS    = 1000UL;
constexpr unsigned long STATE_EVAL_INTERVAL_MS    = 250UL;
constexpr unsigned long COMMS_UPDATE_INTERVAL_MS  = 50UL;
constexpr unsigned long ACTUATOR_UPDATE_INTERVAL_MS = 20UL;
constexpr unsigned long DISPLAY_REFRESH_INTERVAL_MS = 500UL;
constexpr unsigned long HEALTH_POLL_INTERVAL_MS   = 10000UL; // backend liveness ping

// ===========================================================================
// SENSOR BEHAVIOUR
// ===========================================================================
// A reading older than this is reported STALE (never silently reused).
constexpr unsigned long SENSOR_STALE_MS = 5000UL;

// Analog reference/attenuation.  11 dB gives ~0..3.3 V full scale on the S3.
constexpr adc_attenuation_t CONFIG_ADC_ATTENUATION = ADC_11db;

// ---------------------------------------------------------------------------
// Temperature / humidity source.
//
//   0 = DHT22  : digital 1-Wire sensor (temperature + humidity) — DEFAULT
//   1 = ANALOG : TMP36/LM35 + analog humidity module — documented fallback
//
// These are C++ `constexpr`s, not preprocessor macros, so the active source
// MUST be selected with a normal (constant-folded) `if`, never an `#if`.
// ---------------------------------------------------------------------------
constexpr int CONFIG_TEMP_HUMIDITY_SOURCE_DHT22  = 0;
constexpr int CONFIG_TEMP_HUMIDITY_SOURCE_ANALOG = 1;
constexpr int CONFIG_TEMP_HUMIDITY_SOURCE = CONFIG_TEMP_HUMIDITY_SOURCE_DHT22;

// The DHT22 requires >= 2000 ms between reads.  It is sampled on this interval
// (never with delay()); the last valid reading is reused in between and is
// reported STALE once it ages beyond SENSOR_STALE_MS.
constexpr unsigned long CONFIG_DHT_SAMPLE_INTERVAL_MS = 2000UL;

// Push-button debounce window (active-LOW, INPUT_PULLUP).
constexpr unsigned long BUTTON_DEBOUNCE_MS = 30UL;

// Temperature sensor type (analog fallback path only):
//   0 = TMP36 : Vout = 500 mV + 10 mV/degC  ->  C = (mV - 500) / 10
//   1 = LM35  : Vout = 10 mV/degC           ->  C =  mV / 10
constexpr int CONFIG_TEMP_SENSOR_TMP36 = 0;
constexpr int CONFIG_TEMP_SENSOR_LM35  = 1;
constexpr int CONFIG_TEMP_SENSOR_TYPE  = CONFIG_TEMP_SENSOR_TMP36;

// Analog humidity module: linear mapping of the analog output voltage.
// These MUST be calibrated against the real module; the defaults are generic.
constexpr float CONFIG_HUMIDITY_MV_AT_0_PCT   = 0.0f;
constexpr float CONFIG_HUMIDITY_MV_AT_100_PCT = 3000.0f;

// LDR + fixed resistor divider: approximate lux-per-millivolt.  This is a
// rough linearisation, adequate for relative change detection only.
constexpr float CONFIG_LIGHT_LUX_PER_MV = 0.5f;

// Plausibility windows.  Readings outside these are treated as ERROR.
constexpr float TEMP_MIN_VALID_C      = -40.0f;
constexpr float TEMP_MAX_VALID_C      =  125.0f;
constexpr float HUMIDITY_MIN_VALID_PCT = 0.0f;
constexpr float HUMIDITY_MAX_VALID_PCT = 100.0f;
constexpr float LIGHT_MIN_VALID_LUX    = 0.0f;
constexpr float LIGHT_MAX_VALID_LUX    = 100000.0f;

// ===========================================================================
// EVENT ENGINE
// ===========================================================================
constexpr float TEMP_CHANGE_THRESHOLD_C        = 0.5f;
constexpr float HUMIDITY_CHANGE_THRESHOLD_PCT  = 2.0f;
constexpr float LIGHT_CHANGE_THRESHOLD_LUX     = 50.0f;
constexpr unsigned long MOTION_DEBOUNCE_MS     = 100UL;
constexpr unsigned long EVENT_MIN_INTERVAL_MS  = 1000UL;

// ===========================================================================
// CONTEXT BUFFER
// ===========================================================================
constexpr size_t CONFIG_CONTEXT_BUFFER_MAX_EVENTS = 32;
constexpr size_t CONFIG_COMMAND_ID_MAX_LEN        = 64;
constexpr size_t CONFIG_SOURCE_MAX_LEN            = 16;
constexpr size_t CONFIG_DETAIL_MAX_LEN            = 48;

// ===========================================================================
// ACTUATOR BEHAVIOUR
// ===========================================================================
// Servo sweeps to its target in small steps so it never jumps violently.
constexpr int           SERVO_STEP_DEGREES      = 2;
constexpr unsigned long SERVO_STEP_INTERVAL_MS  = 15UL;
constexpr int           SERVO_MIN_PULSE_US      = 500;
constexpr int           SERVO_MAX_PULSE_US      = 2400;

// Documented SAFE STATE (PLAN.md 14): buzzer off, status LED off.  The servo
// HOLDs its last position on communication loss — it is never forced to a
// position that could damage the mechanism, and it is never left driving.

// ===========================================================================
// COMMUNICATION
// ===========================================================================
constexpr uint16_t CONFIG_HTTP_PORT = 80;

// WiFi reconnect backoff (non-blocking): start fast, cap at the max.
constexpr unsigned long WIFI_RETRY_MIN_MS = 1000UL;
constexpr unsigned long WIFI_RETRY_MAX_MS = 30000UL;
// Give up on a single connect attempt after this long and retry with backoff.
constexpr unsigned long WIFI_CONNECT_TIMEOUT_MS = 10000UL;

// NTP (used only for an honest epoch timestamp; falls back to millis()).
constexpr char CONFIG_NTP_SERVER[] = "pool.ntp.org";
constexpr time_t CONFIG_TIME_VALID_AFTER = 1600000000;  // 2020-09-13
