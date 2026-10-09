// ===========================================================================
// Bounded context buffer implementation.
//
// Fixed-size ring buffer; the oldest event is overwritten when full.  No
// dynamic allocation is performed for the buffer itself (ArduinoJson allocates
// transiently while building the summary string, which is bounded).
// ===========================================================================

#include "context_buffer.h"

#include <ArduinoJson.h>
#include <math.h>

void ContextBuffer::begin() {
  head_ = 0;
  count_ = 0;
  seq_ = 0;
  has_latest_ = false;
  latest_ms_ = 0;
  latest_ = SensorSnapshot();
}

void ContextBuffer::pushEvent(const Event& event) {
  Event stored = event;
  stored.seq = ++seq_;
  events_[head_] = stored;
  head_ = (head_ + 1) % CONFIG_CONTEXT_BUFFER_MAX_EVENTS;
  if (count_ < CONFIG_CONTEXT_BUFFER_MAX_EVENTS) {
    ++count_;
  }
}

void ContextBuffer::setLatestReadings(const SensorSnapshot& snapshot,
                                      uint32_t now_ms) {
  latest_ = snapshot;
  latest_ms_ = now_ms;
  has_latest_ = true;
}

uint32_t ContextBuffer::latestAgeMs(uint32_t now_ms) const {
  if (!has_latest_) {
    return UINT32_MAX;
  }
  return (uint32_t)(now_ms - latest_ms_);
}

bool ContextBuffer::hasFreshContext(uint32_t now_ms) const {
  if (!has_latest_) {
    return false;
  }
  return latestAgeMs(now_ms) <= CONTEXT_MAX_AGE_MS;
}

String ContextBuffer::summaryJson() const {
  JsonDocument doc;

  doc["device_id"] = DEVICE_ID;
  doc["event_count"] = (uint32_t)count_;
  doc["latest_age_ms"] = has_latest_ ? latestAgeMs(millis()) : (uint32_t)0;

  // -- latest readings (bounded, no secrets) ------------------------------
  JsonObject readings = doc["latest_readings"].to<JsonObject>();
  auto addScalar = [&](const char* name, const SensorValue& v) {
    JsonObject o = readings[name].to<JsonObject>();
    o["status"] = sensorStatusToString(v.status);
    o["unit"] = v.unit;
    if (v.valid) {
      o["value"] = v.value;
    } else {
      o["value"] = nullptr;  // never fabricate a numeric value
    }
  };
  addScalar("temperature_c", latest_.temperature);
  addScalar("humidity_percent", latest_.humidity);
  addScalar("light_lux", latest_.light);
  {
    JsonObject m = readings["motion"].to<JsonObject>();
    m["status"] = sensorStatusToString(latest_.motion_status);
    m["unit"] = "bool";
    if (latest_.motion_valid) {
      m["value"] = latest_.motion;
    } else {
      m["value"] = nullptr;
    }
  }

  // -- most recent events, oldest -> newest -------------------------------
  JsonArray arr = doc["recent_events"].to<JsonArray>();
  const size_t start =
      (count_ < CONFIG_CONTEXT_BUFFER_MAX_EVENTS) ? 0 : head_;
  for (size_t i = 0; i < count_; ++i) {
    const Event& e = events_[(start + i) % CONFIG_CONTEXT_BUFFER_MAX_EVENTS];
    JsonObject o = arr.add<JsonObject>();
    o["seq"] = e.seq;
    o["type"] = eventTypeToString(e.type);
    o["timestamp_ms"] = e.timestamp_ms;
    if (!isnan(e.value)) {
      o["value"] = e.value;
    }
    if (e.detail[0] != '\0') {
      o["detail"] = e.detail;
    }
  }

  String out;
  serializeJson(doc, out);
  return out;
}
