#pragma once

// ===========================================================================
// Event engine (PLAN.md 13).
//
// Turns the raw sensor stream into a small, bounded set of *typed, debounced*
// events:
//   * change detection  (value moved by more than a threshold)
//   * threshold detection (crossed a configured limit)
//   * motion edge detection (rising / falling), debounced
//
// Events carry a monotonic sequence number and a millis() timestamp.  They are
// pushed into the bounded ContextBuffer, never into unbounded storage.
// ===========================================================================

#include <Arduino.h>
#include <math.h>

#include "config.h"
#include "sensor_manager.h"

class ContextBuffer;  // defined in context_buffer.h

// Event categories, aligned with PLAN.md 13 examples plus command/state events.
enum class EventType : uint8_t {
  BOOT,
  TEMPERATURE_UPDATED,
  HUMIDITY_UPDATED,
  LIGHT_LEVEL_CHANGED,
  TEMPERATURE_HIGH,
  TEMPERATURE_LOW,
  HUMIDITY_HIGH,
  MOTION_DETECTED,
  MOTION_CLEARED,
  SENSOR_ERROR,
  ACTION_APPROVED,
  ACTION_REJECTED,
  COMMAND_ACKNOWLEDGED,
  COMMAND_REJECTED,
  FALLBACK_ACTIVATED,
  AGENT_TIMEOUT,
  STATE_TRANSITION,
  RECOVERY,
  BUTTON_ACK,                // operator acknowledged a local alert
  SENSOR_REREAD_REQUESTED,   // operator requested an immediate sensor re-read
};

const char* eventTypeToString(EventType type);

// A single bounded event record.
struct Event {
  EventType type = EventType::BOOT;
  uint32_t seq = 0;
  uint32_t timestamp_ms = 0;
  float value = NAN;  // optional numeric payload
  char detail[CONFIG_DETAIL_MAX_LEN] = {0};
};

class EventEngine {
 public:
  void begin(uint32_t now_ms);

  // Evaluate the latest snapshot and emit any events into `context`.
  void update(const SensorSnapshot& snapshot, uint32_t now_ms, ContextBuffer& context);

  // Emit an externally-generated event (command result, state transition, ...).
  void emit(EventType type, float value, const char* detail,
            uint32_t now_ms, ContextBuffer& context);

 private:
  // Previous values used for change/threshold edge detection.
  bool have_temp_ = false;
  float last_temp_ = NAN;
  bool temp_high_ = false;
  bool temp_low_ = false;

  bool have_humidity_ = false;
  float last_humidity_ = NAN;
  bool humidity_high_ = false;

  bool have_light_ = false;
  float last_light_ = NAN;

  bool have_motion_ = false;
  bool last_motion_ = false;
  uint32_t motion_edge_ms_ = 0;

  // Per-channel debounce so a noisy sensor cannot flood the buffer.
  uint32_t last_temp_event_ms_ = 0;
  uint32_t last_humidity_event_ms_ = 0;
  uint32_t last_light_event_ms_ = 0;
};
