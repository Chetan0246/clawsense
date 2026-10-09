// ===========================================================================
// Local fallback controller implementation.
//
// Handles invalid/stale sensor data safely: a rule that depends on a channel
// only fires when that channel is valid and fresh.  If nothing is usable the
// controller produces a safe no_op rather than guessing.
// ===========================================================================

#include "local_controller.h"

// Rule identifiers — kept identical to backend/app/services/fallback_controller.py.
static constexpr char RULE_NOMINAL[]           = "FALLBACK_NOMINAL";
static constexpr char RULE_HIGH_TEMPERATURE[]  = "FALLBACK_HIGH_TEMPERATURE";
static constexpr char RULE_LOW_TEMPERATURE[]   = "FALLBACK_LOW_TEMPERATURE";
static constexpr char RULE_HIGH_HUMIDITY[]     = "FALLBACK_HIGH_HUMIDITY";
static constexpr char RULE_MOTION[]            = "FALLBACK_MOTION";

static int clampInt(int v, int lo, int hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

static bool freshReading(const SensorValue& v, uint32_t now_ms) {
  if (!v.valid) return false;
  return (uint32_t)(now_ms - v.last_ok_ms) <= CONTEXT_MAX_AGE_MS;
}

void LocalController::begin() {
  last_rule_[0] = '\0';
  last_emit_ms_ = 0;
}

bool LocalController::evaluate(const SensorSnapshot& s, uint32_t now_ms,
                               LocalDecision& decision) {
  decision = LocalDecision();
  strlcpy(decision.rule, RULE_NOMINAL, sizeof(decision.rule));

  const bool temp_ok = freshReading(s.temperature, now_ms);
  const bool humidity_ok = freshReading(s.humidity, now_ms);

  // -- R1: high temperature -> red LED + bounded buzzer --------------------
  if (temp_ok && s.temperature.value > TEMP_HIGH_C) {
    strlcpy(decision.rule, RULE_HIGH_TEMPERATURE, sizeof(decision.rule));
    decision.from_valid_data = true;

    Action led;
    led.name = ActionName::SET_STATUS_LED;
    led.color = LedColor::RED;
    strlcpy(led.source, "fallback", sizeof(led.source));
    strlcpy(led.reason, "fallback: temperature above high threshold",
            sizeof(led.reason));

    Action beep;
    beep.name = ActionName::BUZZER_BEEP;
    beep.duration_ms =
        clampInt(FALLBACK_ALERT_BEEP_MS, BUZZER_MIN_MS, BUZZER_MAX_MS);
    strlcpy(beep.source, "fallback", sizeof(beep.source));
    strlcpy(beep.reason, "fallback: high-temperature alert",
            sizeof(beep.reason));

    decision.actions[0] = led;
    decision.actions[1] = beep;
    decision.count = 2;
  }
  // -- R2: low temperature -> yellow LED -----------------------------------
  else if (temp_ok && s.temperature.value < TEMP_LOW_C) {
    strlcpy(decision.rule, RULE_LOW_TEMPERATURE, sizeof(decision.rule));
    decision.from_valid_data = true;

    Action led;
    led.name = ActionName::SET_STATUS_LED;
    led.color = LedColor::YELLOW;
    strlcpy(led.source, "fallback", sizeof(led.source));
    strlcpy(led.reason, "fallback: temperature below low threshold",
            sizeof(led.reason));
    decision.actions[0] = led;
    decision.count = 1;
  }
  // -- R3: high humidity -> yellow LED -------------------------------------
  else if (humidity_ok && s.humidity.value > HUMIDITY_HIGH_PERCENT) {
    strlcpy(decision.rule, RULE_HIGH_HUMIDITY, sizeof(decision.rule));
    decision.from_valid_data = true;

    Action led;
    led.name = ActionName::SET_STATUS_LED;
    led.color = LedColor::YELLOW;
    strlcpy(led.source, "fallback", sizeof(led.source));
    strlcpy(led.reason, "fallback: humidity above high threshold",
            sizeof(led.reason));
    decision.actions[0] = led;
    decision.count = 1;
  }
  // -- R4: motion -> observation angle (clamped to safe range) -------------
  else if (s.motion_valid && s.motion && s.motion_status == SensorStatus::OK) {
    strlcpy(decision.rule, RULE_MOTION, sizeof(decision.rule));
    decision.from_valid_data = true;

    Action servo;
    servo.name = ActionName::SERVO_MOVE;
    servo.angle_degrees = clampInt(FALLBACK_OBSERVATION_ANGLE,
                                   SERVO_MIN_DEGREES, SERVO_MAX_DEGREES);
    strlcpy(servo.source, "fallback", sizeof(servo.source));
    strlcpy(servo.reason, "fallback: motion detected; observing",
            sizeof(servo.reason));
    decision.actions[0] = servo;
    decision.count = 1;
  }
  // -- R0: nominal ---------------------------------------------------------
  else {
    Action noop;
    noop.name = ActionName::NO_OP;
    strlcpy(noop.source, "fallback", sizeof(noop.source));
    strlcpy(noop.reason, "fallback: no action required", sizeof(noop.reason));
    decision.actions[0] = noop;
    decision.count = 1;
  }

  // Decide whether to (re)apply.  Emit on rule change or periodic refresh.
  const bool rule_changed = strcmp(decision.rule, last_rule_) != 0;
  const bool refresh_due =
      (uint32_t)(now_ms - last_emit_ms_) >= LOCAL_REISSUE_MS;

  if (rule_changed || refresh_due) {
    strlcpy(last_rule_, decision.rule, sizeof(last_rule_));
    last_emit_ms_ = now_ms;
    return true;
  }
  return false;
}
