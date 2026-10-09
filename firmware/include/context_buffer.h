#pragma once

// ===========================================================================
// Bounded contextual memory (PLAN.md 13).
//
// A fixed-size ring buffer of the most recent events plus the latest sensor
// snapshot.  Memory usage is bounded at compile time — no dynamic allocation,
// no unbounded growth.  The agent/backend receives a concise summary via
// summaryJson() rather than the raw event stream.
//
// The backend mirror of this is backend/app/services/context_memory.py.
// ===========================================================================

#include <Arduino.h>

#include "config.h"
#include "event_engine.h"
#include "sensor_manager.h"

class ContextBuffer {
 public:
  void begin();

  // Append an event; overwrites the oldest entry when full.
  void pushEvent(const Event& event);

  // Record the latest telemetry snapshot (used for context-freshness checks
  // and the /telemetry endpoint).
  void setLatestReadings(const SensorSnapshot& snapshot, uint32_t now_ms);

  const Event* events() const { return events_; }
  size_t eventCount() const { return count_; }

  const SensorSnapshot& latest() const { return latest_; }
  bool hasLatest() const { return has_latest_; }

  // Age of the most recent snapshot in milliseconds (UINT32_MAX if none).
  uint32_t latestAgeMs(uint32_t now_ms) const;

  // True when a usable snapshot exists and is within CONTEXT_MAX_AGE_MS.
  bool hasFreshContext(uint32_t now_ms) const;

  // Compact, bounded summary for the backend/agent.  Excludes secrets and
  // unnecessary personal data (PLAN.md 13).
  String summaryJson() const;

 private:
  Event events_[CONFIG_CONTEXT_BUFFER_MAX_EVENTS];
  size_t head_ = 0;   // index of the next write slot
  size_t count_ = 0;  // number of valid entries (<= MAX)
  uint32_t seq_ = 0;  // monotonic event sequence

  SensorSnapshot latest_;
  uint32_t latest_ms_ = 0;
  bool has_latest_ = false;
};
