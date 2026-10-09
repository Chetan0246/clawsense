// ===========================================================================
// Push-button implementation.
//
// Active-LOW: a pressed button reads LOW, a released button reads HIGH thanks
// to the internal pull-up.  A raw transition must persist for
// BUTTON_DEBOUNCE_MS before it becomes the debounced level; only the
// released -> pressed edge sets the one-shot flag.
// ===========================================================================

#include "buttons.h"

void Buttons::begin() {
  // Held high by the internal pull-up so a pin never floats, whether or not a
  // button is fitted; update() only reports presses when enabled.
  pinMode(CONFIG_PIN_BUTTON_1, INPUT_PULLUP);
  pinMode(CONFIG_PIN_BUTTON_2, INPUT_PULLUP);
  ack_ = Debounced();
  reread_ = Debounced();
}

void Buttons::updateOne(Debounced& b, int pin, uint32_t now_ms) {
  const bool raw = (digitalRead(pin) == HIGH);  // true = released (active-LOW)
  if (raw != b.last_raw) {
    b.last_raw = raw;
    b.last_change_ms = now_ms;
  }
  if ((uint32_t)(now_ms - b.last_change_ms) < BUTTON_DEBOUNCE_MS) {
    return;  // still bouncing / not yet stable
  }
  if (raw == b.stable) {
    return;  // no debounced change
  }
  const bool was_released = b.stable;
  b.stable = raw;
  if (was_released && !raw) {
    b.pressed_flag = true;  // released -> pressed
  }
}

void Buttons::update(uint32_t now_ms) {
#if CONFIG_ENABLE_BUTTONS
  updateOne(ack_, CONFIG_PIN_BUTTON_1, now_ms);
  updateOne(reread_, CONFIG_PIN_BUTTON_2, now_ms);
#else
  (void)now_ms;
#endif
}

bool Buttons::consumeAck() {
  if (!ack_.pressed_flag) {
    return false;
  }
  ack_.pressed_flag = false;
  return true;
}

bool Buttons::consumeReread() {
  if (!reread_.pressed_flag) {
    return false;
  }
  reread_.pressed_flag = false;
  return true;
}
