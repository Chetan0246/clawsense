#pragma once

// ===========================================================================
// Actuator manager (PLAN.md 14).
//
// This is the ONLY module in the firmware that touches GPIO / PWM.  Everything
// else proposes actions; only this class drives hardware.  Consequences:
//   * every value is clamped here as a final, independent line of defence;
//   * the servo sweeps smoothly to its target and never jumps violently;
//   * the buzzer sounds only for its bounded duration, then switches off;
//   * the status indication is three DISCRETE LEDs (green/yellow/red, active
//     HIGH) and exactly one is driven at a time (or all off);
//   * the documented SAFE STATE is: buzzer off, LEDs off, servo HOLDS position.
//
// Safe-state rationale (PLAN.md 14): forcing a servo to 0 degrees on comms loss
// could be mechanically unsafe, so on loss of communication the servo simply
// stays where it is (it is not commanded anywhere) — it is never left hunting.
// ===========================================================================

#include <Arduino.h>

#include "action.h"
#include "config.h"

struct ActuatorState {
  int servo_target = 90;    // commanded target angle
  int servo_current = 90;   // current swept angle (what the servo is told)
  bool servo_attached = false;

  bool buzzer_active = false;
  uint32_t buzzer_end_ms = 0;

  LedColor led = LedColor::OFF;

  uint32_t last_action_ms = 0;
  char last_action[24] = {0};
  char last_result[32] = {0};
};

class ActuatorManager {
 public:
  void begin();

  // Non-blocking: advances the servo sweep and switches the buzzer off when its
  // bounded duration expires.  Call every loop().
  void update(uint32_t now_ms);

  // Apply an already-validated action.  Values are re-clamped defensively.
  // Returns true when the action was applied to the hardware model.
  bool applyAction(const Action& action, uint32_t now_ms);

  // Directly set the status LED (used for state indication).
  // green -> green LED, yellow -> yellow LED, red -> red LED, off -> all off.
  void setStatusLed(LedColor color);

  // Return outputs to the documented safe state (buzzer off, LED off; servo
  // holds its current position).
  void safeState(uint32_t now_ms);

  const ActuatorState& state() const { return state_; }

  // True while the servo is still moving toward its target.
  bool servoBusy() const { return state_.servo_current != state_.servo_target; }

 private:
  void writeLed(LedColor color);
  void startBuzzer(int duration_ms, uint32_t now_ms);
  void stopBuzzer();
  void setServoTarget(int angle);

  ActuatorState state_;
  uint32_t last_step_ms_ = 0;
};
