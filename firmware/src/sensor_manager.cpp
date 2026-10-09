// ===========================================================================
// Sensor manager implementation.
//
// Design notes:
//   * Everything is millis()-driven; update() never blocks and never delays.
//   * Temperature/humidity come from a DHT22 by default; an analog TMP36/LM35
//     + analog humidity module fallback path can be selected in config.h.
//   * The DHT22 needs >= 2000 ms between reads, so it is only read on the
//     CONFIG_DHT_SAMPLE_INTERVAL_MS boundary; the previous reading is reused in
//     between and flagged STALE once it ages past SENSOR_STALE_MS.
//   * A failed DHT22 read is reported ERROR with NO value (never 0, never a
//     fabricated reading).  The analog path keeps its previous value but is
//     still flagged ERROR.
//   * ADC reads use analogReadMilliVolts(), which applies the eFuse factory
//     calibration on the ESP32-S3 — far more accurate than raw analogRead().
// ===========================================================================

#include "sensor_manager.h"

#include <DHT.h>
#include <math.h>

// DHT22 on CONFIG_PIN_DHT_DATA.  The library is only exercised when
// CONFIG_TEMP_HUMIDITY_SOURCE selects the DHT22 path (a normal `if`, below).
static DHT g_dht(CONFIG_PIN_DHT_DATA, DHT22);

const char* sensorStatusToString(SensorStatus status) {
  switch (status) {
    case SensorStatus::OK:             return "OK";
    case SensorStatus::STALE:          return "STALE";
    case SensorStatus::ERROR:          return "ERROR";
    case SensorStatus::NOT_CONFIGURED: return "NOT_CONFIGURED";
    case SensorStatus::UNAVAILABLE:    return "UNAVAILABLE";
  }
  return "ERROR";
}

bool SensorSnapshot::hasFreshContext(uint32_t now_ms) const {
  if (!temperature.valid) {
    return false;
  }
  return (uint32_t)(now_ms - temperature.last_ok_ms) <= CONTEXT_MAX_AGE_MS;
}

// -- SensorManager ----------------------------------------------------------

void SensorManager::begin() {
  snapshot_ = SensorSnapshot();
  last_dht_ms_ = 0;
  force_sample_ = false;

  // Both temperature/humidity channels declare their unit regardless of source.
  snapshot_.temperature.unit = "C";
  snapshot_.humidity.unit = "%";

  // The source is a C++ `constexpr`, so it MUST be selected with a normal
  // (constant-folded) `if`, never an `#if` (see config.h).
  if (CONFIG_TEMP_HUMIDITY_SOURCE == CONFIG_TEMP_HUMIDITY_SOURCE_DHT22) {
    g_dht.begin();
  }

  if (CONFIG_TEMP_HUMIDITY_SOURCE == CONFIG_TEMP_HUMIDITY_SOURCE_ANALOG) {
    // -- analog fallback path --------------------------------------------
#if CONFIG_ENABLE_TEMPERATURE
    pinMode(CONFIG_PIN_TEMP_ADC, INPUT);
    analogSetPinAttenuation(CONFIG_PIN_TEMP_ADC, CONFIG_ADC_ATTENUATION);
    snapshot_.temperature.configured = true;
    snapshot_.temperature.status = SensorStatus::ERROR;  // until first good read
#else
    snapshot_.temperature.status = SensorStatus::NOT_CONFIGURED;
#endif
#if CONFIG_ENABLE_HUMIDITY
    pinMode(CONFIG_PIN_HUMID_ADC, INPUT);
    analogSetPinAttenuation(CONFIG_PIN_HUMID_ADC, CONFIG_ADC_ATTENUATION);
    snapshot_.humidity.configured = true;
    snapshot_.humidity.status = SensorStatus::ERROR;
#else
    snapshot_.humidity.status = SensorStatus::NOT_CONFIGURED;
#endif
  } else {
    // -- DHT22 path (default) --------------------------------------------
#if CONFIG_ENABLE_TEMPERATURE
    snapshot_.temperature.configured = true;
    snapshot_.temperature.status = SensorStatus::ERROR;  // until first good read
#else
    snapshot_.temperature.status = SensorStatus::NOT_CONFIGURED;
#endif
#if CONFIG_ENABLE_HUMIDITY
    snapshot_.humidity.configured = true;
    snapshot_.humidity.status = SensorStatus::ERROR;
#else
    snapshot_.humidity.status = SensorStatus::NOT_CONFIGURED;
#endif
  }

  // -- third sensor slot: light ONLY if actually configured ---------------
  // Default (slot = NONE) reports NOT_CONFIGURED with no value; a reading is
  // never fabricated (PLAN.md 2.2 / 3 / 23).
#if CONFIG_ENABLE_LIGHT
  pinMode(CONFIG_PIN_LIGHT_ADC, INPUT);
  analogSetPinAttenuation(CONFIG_PIN_LIGHT_ADC, CONFIG_ADC_ATTENUATION);
  snapshot_.light.configured = true;
  snapshot_.light.unit = "lux";
  snapshot_.light.status = SensorStatus::ERROR;  // until first good read
#else
  snapshot_.light.configured = false;
  snapshot_.light.valid = false;
  snapshot_.light.value = NAN;
  snapshot_.light.unit = "lux";
  snapshot_.light.status = SensorStatus::NOT_CONFIGURED;
#endif

#if CONFIG_ENABLE_MOTION
  // PIR modules idle low and drive high on detection.
  pinMode(CONFIG_PIN_PIR, INPUT);
  snapshot_.motion_status = SensorStatus::OK;
#else
  snapshot_.motion_status = SensorStatus::NOT_CONFIGURED;
#endif

  started_ = true;
}

void SensorManager::update(uint32_t now_ms) {
  if (!started_) {
    begin();
  }
  const bool due = force_sample_ ||
                   (uint32_t)(now_ms - last_sample_ms_) >= SENSOR_SAMPLE_INTERVAL_MS;
  if (!due) {
    return;
  }
  force_sample_ = false;
  last_sample_ms_ = now_ms;
  sampleNow(now_ms);
  refreshStaleness(now_ms);
}

void SensorManager::refreshStaleness(uint32_t now_ms) {
  auto markStale = [&](SensorValue& v) {
    if (v.configured && v.valid && v.status == SensorStatus::OK &&
        (uint32_t)(now_ms - v.last_ok_ms) > SENSOR_STALE_MS) {
      v.status = SensorStatus::STALE;
    }
  };
  markStale(snapshot_.temperature);
  markStale(snapshot_.humidity);
  markStale(snapshot_.light);
}

void SensorManager::sampleNow(uint32_t now_ms) {
  snapshot_.timestamp_ms = now_ms;
  if (CONFIG_TEMP_HUMIDITY_SOURCE == CONFIG_TEMP_HUMIDITY_SOURCE_DHT22) {
    sampleDht(now_ms);
  } else {
    sampleTemperatureAnalog(now_ms);
    sampleHumidityAnalog(now_ms);
  }
  sampleLight(now_ms);
  sampleMotion(now_ms);
}

float SensorManager::readMilliVolts(int pin) {
  // Average a few samples to reject ADC noise without blocking for long.
  constexpr int kSamples = 8;
  uint32_t total = 0;
  for (int i = 0; i < kSamples; ++i) {
    total += analogReadMilliVolts(pin);
  }
  return (float)total / (float)kSamples;
}

// -- DHT22 path -------------------------------------------------------------
void SensorManager::sampleDht(uint32_t now_ms) {
  // Respect the DHT22 minimum interval.  Between reads we simply keep the last
  // reading (no blocking delay is ever used).
  if (last_dht_ms_ != 0 &&
      (uint32_t)(now_ms - last_dht_ms_) < CONFIG_DHT_SAMPLE_INTERVAL_MS) {
    return;
  }
  last_dht_ms_ = now_ms;

  const float celsius = g_dht.readTemperature();  // NAN on checksum/timeout
  const float pct = g_dht.readHumidity();

#if CONFIG_ENABLE_TEMPERATURE
  {
    SensorValue& t = snapshot_.temperature;
    if (isnan(celsius) || celsius < TEMP_MIN_VALID_C ||
        celsius > TEMP_MAX_VALID_C) {
      // A failed read yields ERROR with NO value — never 0, never fabricated.
      t.status = SensorStatus::ERROR;
      t.valid = false;
      t.value = NAN;
      CS_LOGW("DHT22 temperature read failed");
    } else {
      t.value = celsius;
      t.valid = true;
      t.last_ok_ms = now_ms;
      t.status = SensorStatus::OK;
    }
  }
#endif

#if CONFIG_ENABLE_HUMIDITY
  {
    SensorValue& h = snapshot_.humidity;
    if (isnan(pct) || pct < HUMIDITY_MIN_VALID_PCT ||
        pct > HUMIDITY_MAX_VALID_PCT) {
      h.status = SensorStatus::ERROR;
      h.valid = false;
      h.value = NAN;
      CS_LOGW("DHT22 humidity read failed");
    } else {
      h.value = pct;
      h.valid = true;
      h.last_ok_ms = now_ms;
      h.status = SensorStatus::OK;
    }
  }
#endif
}

// -- analog fallback path ---------------------------------------------------
void SensorManager::sampleTemperatureAnalog(uint32_t now_ms) {
  SensorValue& s = snapshot_.temperature;
#if !CONFIG_ENABLE_TEMPERATURE
  s.status = SensorStatus::NOT_CONFIGURED;
  return;
#else
  const float mv = readMilliVolts(CONFIG_PIN_TEMP_ADC);
  // CONFIG_TEMP_SENSOR_TYPE is a C++ `constexpr`, not a preprocessor macro, so
  // it MUST be selected with a normal (constant-folded) `if`.  Using it in an
  // `#if` makes both identifiers evaluate to 0, so the condition is always true
  // and the LM35 formula would be used even for the default TMP36.
  float celsius;
  if (CONFIG_TEMP_SENSOR_TYPE == CONFIG_TEMP_SENSOR_LM35) {
    celsius = mv / 10.0f;             // LM35 : 10 mV/degC
  } else {
    celsius = (mv - 500.0f) / 10.0f;  // TMP36: 500 mV offset, 10 mV/degC
  }

  if (isnan(celsius) || celsius < TEMP_MIN_VALID_C || celsius > TEMP_MAX_VALID_C) {
    // Keep the previous value; flag the channel rather than reporting a lie.
    s.status = SensorStatus::ERROR;
    CS_LOGW("temperature implausible: %.1f C (%.0f mV)", celsius, mv);
    return;
  }
  s.value = celsius;
  s.valid = true;
  s.last_ok_ms = now_ms;
  s.status = SensorStatus::OK;
#endif
}

void SensorManager::sampleHumidityAnalog(uint32_t now_ms) {
  SensorValue& s = snapshot_.humidity;
#if !CONFIG_ENABLE_HUMIDITY
  s.status = SensorStatus::NOT_CONFIGURED;
  return;
#else
  const float mv = readMilliVolts(CONFIG_PIN_HUMID_ADC);
  const float span = CONFIG_HUMIDITY_MV_AT_100_PCT - CONFIG_HUMIDITY_MV_AT_0_PCT;
  float pct = (span != 0.0f)
                  ? (mv - CONFIG_HUMIDITY_MV_AT_0_PCT) * 100.0f / span
                  : NAN;

  if (isnan(pct) || pct < HUMIDITY_MIN_VALID_PCT || pct > HUMIDITY_MAX_VALID_PCT) {
    s.status = SensorStatus::ERROR;
    CS_LOGW("humidity implausible: %.1f %% (%.0f mV)", pct, mv);
    return;
  }
  s.value = pct;
  s.valid = true;
  s.last_ok_ms = now_ms;
  s.status = SensorStatus::OK;
#endif
}

void SensorManager::sampleLight(uint32_t now_ms) {
  SensorValue& s = snapshot_.light;
#if !CONFIG_ENABLE_LIGHT
  // Third-sensor slot is not a light sensor: report NOT_CONFIGURED, no value.
  s.configured = false;
  s.valid = false;
  s.value = NAN;
  s.unit = "lux";
  s.status = SensorStatus::NOT_CONFIGURED;
  (void)now_ms;
  return;
#else
  const float mv = readMilliVolts(CONFIG_PIN_LIGHT_ADC);
  float lux = mv * CONFIG_LIGHT_LUX_PER_MV;

  if (isnan(lux) || lux < LIGHT_MIN_VALID_LUX || lux > LIGHT_MAX_VALID_LUX) {
    s.status = SensorStatus::ERROR;
    CS_LOGW("light implausible: %.1f lux (%.0f mV)", lux, mv);
    return;
  }
  s.value = lux;
  s.valid = true;
  s.last_ok_ms = now_ms;
  s.status = SensorStatus::OK;
#endif
}

void SensorManager::sampleMotion(uint32_t now_ms) {
#if !CONFIG_ENABLE_MOTION
  snapshot_.motion_status = SensorStatus::NOT_CONFIGURED;
  (void)now_ms;
  return;
#else
  const bool raw = digitalRead(CONFIG_PIN_PIR) == HIGH;
  if (raw != snapshot_.motion) {
    snapshot_.motion_last_change_ms = now_ms;
  }
  snapshot_.motion = raw;
  snapshot_.motion_valid = true;
  snapshot_.motion_status = SensorStatus::OK;
#endif
}
