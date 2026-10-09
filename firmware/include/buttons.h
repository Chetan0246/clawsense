#pragma once

// ===========================================================================
// Push-button input (PLAN.md 3, 14).
//
// Two active-LOW buttons wired to GND with INPUT_PULLUP:
//   BUTTON 1 : acknowledge / clear a local alert (operator acknowledgement)
//   BUTTON 2 : request an immediate sensor re-read
//
// SAFETY: buttons are LOCAL, NON-ACTUATOR inputs.  They NEVER drive the servo,
// buzzer or status LEDs directly and never bypass the on-device safety
// supervisor.  A press only sets a one-shot flag that the main loop surfaces
// as an audit event (or, for button 2, a sensor re-read request).
//
// Debounce is fully non-blocking: a raw level must be stable for
// BUTTON_DEBOUNCE_MS before it is accepted.
// ===========================================================================

#include <Arduino.h>

#include "config.h"

class Buttons {
 public:
  void begin();

  // Call every loop().  Non-blocking.
  void update(uint32_t now_ms);

  // One-shot consumers: return true at most once per debounced press.
  bool consumeAck();     // BUTTON 1 pressed
  bool consumeReread();  // BUTTON 2 pressed

 private:
  struct Debounced {
    bool stable = true;            // debounced level (true = released/HIGH)
    bool last_raw = true;          // last raw level seen
    uint32_t last_change_ms = 0;   // when the raw level last changed
    bool pressed_flag = false;     // one-shot press latch
  };

  static void updateOne(Debounced& b, int pin, uint32_t now_ms);

  Debounced ack_;
  Debounced reread_;
};
