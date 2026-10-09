#pragma once

// ===========================================================================
// Local offline fallback controller (PLAN.md 12).
//
// Independent of the LLM and the network.  Implements the SAME documented
// rules as backend/app/services/fallback_controller.py:
//
//   R1 HIGH_TEMPERATURE : temperature_c > TEMP_HIGH_C
//                         -> status LED red + short bounded buzzer
//   R2 LOW_TEMPERATURE  : temperature_c < TEMP_LOW_C
//                         -> status LED yellow
//   R3 HIGH_HUMIDITY    : humidity_percent > HUMIDITY_HIGH_PERCENT
//                         -> status LED yellow
//   R4 MOTION           : motion == true
//                         -> servo to FALLBACK_OBSERVATION_ANGLE (clamped)
//   R0 NOMINAL          : otherwise -> no_op
//
// Every produced value is range-clamped; the actions are still re-validated by
// the on-device safety supervisor before execution, so a fallback action can
// never exceed an actuator's safe range.
// ===========================================================================

#include <Arduino.h>

#include "action.h"
#include "config.h"
#include "sensor_manager.h"

struct LocalDecision {
  size_t count = 0;                 // number of actions (0..2)
  Action actions[2];                // at most LED + buzzer for R1
  char rule[32] = "";               // rule code, e.g. FALLBACK_HIGH_TEMPERATURE
  bool from_valid_data = false;     // false when no usable sensor data
};

class LocalController {
 public:
  void begin();

  // Evaluate the current snapshot.  Returns true when the caller should APPLY
  // `decision` now (rule changed, or periodic re-issue elapsed).  `decision` is
  // always populated.
  bool evaluate(const SensorSnapshot& snapshot, uint32_t now_ms,
                LocalDecision& decision);

  const char* lastRule() const { return last_rule_; }

 private:
  char last_rule_[32] = "";
  uint32_t last_emit_ms_ = 0;
};
