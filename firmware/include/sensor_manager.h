#pragma once

// ===========================================================================
// Sensor manager (PLAN.md 14).
//
// Responsibilities:
//   * non-blocking sampling at a fixed millis()-based interval (no delay());
//   * DHT22 temperature/humidity (default) with an analog fallback path;
//   * ADC -> engineering-unit conversion using the calibrated ADC;
//   * plausibility checks (out-of-range -> ERROR);
//   * per-sensor status OK / STALE / ERROR / NOT_CONFIGURED;
//   * NEVER coerces a failed reading to 0 — a failed DHT22 read is reported
//     ERROR with no value, and the value is NAN until a good read arrives.
//
// The DHT22 needs >= 2000 ms between reads, so it is sampled on
// CONFIG_DHT_SAMPLE_INTERVAL_MS and the previous reading is reused in between.
// ===========================================================================

#include <Arduino.h>
#include <math.h>

#include "config.h"

// Mirrors backend SensorStatus (app/schemas/telemetry.py).
enum class SensorStatus : uint8_t {
  OK,
  STALE,
  ERROR,
  NOT_CONFIGURED,
  UNAVAILABLE,
};

const char* sensorStatusToString(SensorStatus status);

// One scalar sensor channel.
struct SensorValue {
  bool configured = false;             // feature flag enabled
  bool valid = false;                  // at least one good reading so far
  float value = NAN;                   // last good value (NAN until read)
  SensorStatus status = SensorStatus::NOT_CONFIGURED;
  uint32_t last_ok_ms = 0;             // millis() of last good conversion
  const char* unit = "";
};

// A coherent snapshot of every channel at one instant.
struct SensorSnapshot {
  uint32_t timestamp_ms = 0;           // millis() when sampled

  SensorValue temperature;             // degC
  SensorValue humidity;                // percent
  SensorValue light;                   // lux (approximate)

  bool motion = false;                 // PIR state (digital)
  bool motion_valid = false;
  SensorStatus motion_status = SensorStatus::NOT_CONFIGURED;
  uint32_t motion_last_change_ms = 0;

  // True when at least the temperature channel has a usable recent value.
  bool hasFreshContext(uint32_t now_ms) const;
};

class SensorManager {
 public:
  void begin();
  void update(uint32_t now_ms);        // call every loop(); samples on interval

  const SensorSnapshot& snapshot() const { return snapshot_; }

  // Force a synchronous sample (used once in setup() to avoid a cold start).
  void sampleNow(uint32_t now_ms);

  // Request an extra sample on the next update() (e.g. the re-read button).
  // The DHT22 minimum read interval is still respected internally.
  void requestImmediateSample() { force_sample_ = true; }

 private:
  void sampleDht(uint32_t now_ms);              // DHT22 path (both channels)
  void sampleTemperatureAnalog(uint32_t now_ms); // analog fallback path
  void sampleHumidityAnalog(uint32_t now_ms);    // analog fallback path
  void sampleLight(uint32_t now_ms);
  void sampleMotion(uint32_t now_ms);

  // Mark a channel STALE when its last good reading is older than
  // SENSOR_STALE_MS.  A stale value is never silently reused as if fresh.
  void refreshStaleness(uint32_t now_ms);

  // Read the calibrated ADC in millivolts (averaged) from an ADC1 pin.
  static float readMilliVolts(int pin);

  SensorSnapshot snapshot_;
  uint32_t last_sample_ms_ = 0;
  uint32_t last_dht_ms_ = 0;     // last DHT22 read (>= 2000 ms spacing)
  bool force_sample_ = false;    // set by requestImmediateSample()
  bool started_ = false;
};
