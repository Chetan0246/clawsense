// ===========================================================================
// Actuator manager implementation.
//
// Hardware notes:
//   * The servo is powered from a SEPARATE 5 V supply with a COMMON GROUND
//     (PLAN.md 3/4).  Never power a servo from a GPIO or the 3V3 rail.
//   * The buzzer is driven with tone()/noTone(), which use the ESP32 LEDC
//     peripheral (PWM) — no blocking delay is ever used for the beep.
//   * The status indication is three DISCRETE LEDs (active HIGH), driven one at
//     a time: green / yellow / red, or all off.
// ===========================================================================

#include "actuator_manager.h"

#if CONFIG_ENABLE_SERVO
#include <ESP32Servo.h>
static Servo g_servo;
#endif

static constexpr int BUZZER_FREQ_HZ = 2000;

void ActuatorManager::begin() {
  state_ = ActuatorState();
  state_.servo_target = (SERVO_MIN_DEGREES + SERVO_MAX_DEGREES) / 2;
  state_.servo_current = state_.servo_target;
  state_.led = LedColor::OFF;

#if CONFIG_ENABLE_SERVO
  g_servo.setPeriodHertz(50);
  g_servo.attach(CONFIG_PIN_SERVO, SERVO_MIN_PULSE_US, SERVO_MAX_PULSE_US);
  g_servo.write(state_.servo_current);
  state_.servo_attached = true;
  CS_LOGI("servo attached on GPIO%d, centre=%d", CONFIG_PIN_SERVO,
          state_.servo_current);
#endif

#if CONFIG_ENABLE_BUZZER
  pinMode(CONFIG_PIN_BUZZER, OUTPUT);
  digitalWrite(CONFIG_PIN_BUZZER, LOW);
#endif

#if CONFIG_ENABLE_STATUS_LED
  pinMode(CONFIG_PIN_LED_GREEN, OUTPUT);
  pinMode(CONFIG_PIN_LED_YELLOW, OUTPUT);
  pinMode(CONFIG_PIN_LED_RED, OUTPUT);
#endif

  writeLed(LedColor::OFF);
  state_.buzzer_active = false;
  state_.buzzer_end_ms = 0;
}

void ActuatorManager::writeLed(LedColor color) {
#if !CONFIG_ENABLE_STATUS_LED
  (void)color;
  return;
#else
  // Exactly one discrete LED is driven at a time (or all off).  Active HIGH.
  bool green = false, yellow = false, red = false;
  switch (color) {
    case LedColor::GREEN:  green = true;  break;
    case LedColor::YELLOW: yellow = true; break;
    case LedColor::RED:    red = true;    break;
    case LedColor::OFF:
    case LedColor::UNKNOWN:
    default:               break;         // all off
  }
  digitalWrite(CONFIG_PIN_LED_GREEN, green ? HIGH : LOW);
  digitalWrite(CONFIG_PIN_LED_YELLOW, yellow ? HIGH : LOW);
  digitalWrite(CONFIG_PIN_LED_RED, red ? HIGH : LOW);
  state_.led = color;
#endif
}

void ActuatorManager::setStatusLed(LedColor color) {
  if (color == LedColor::UNKNOWN) {
    return;  // never drive an invalid colour
  }
  writeLed(color);
}

void ActuatorManager::setServoTarget(int angle) {
  if (angle < SERVO_MIN_DEGREES) angle = SERVO_MIN_DEGREES;
  if (angle > SERVO_MAX_DEGREES) angle = SERVO_MAX_DEGREES;
  state_.servo_target = angle;
}

void ActuatorManager::startBuzzer(int duration_ms, uint32_t now_ms) {
  if (duration_ms < BUZZER_MIN_MS) duration_ms = BUZZER_MIN_MS;
  if (duration_ms > BUZZER_MAX_MS) duration_ms = BUZZER_MAX_MS;
#if CONFIG_ENABLE_BUZZER
  tone(CONFIG_PIN_BUZZER, BUZZER_FREQ_HZ);
#endif
  state_.buzzer_active = true;
  state_.buzzer_end_ms = now_ms + (uint32_t)duration_ms;
}

void ActuatorManager::stopBuzzer() {
#if CONFIG_ENABLE_BUZZER
  noTone(CONFIG_PIN_BUZZER);
  digitalWrite(CONFIG_PIN_BUZZER, LOW);
#endif
  state_.buzzer_active = false;
}

void ActuatorManager::update(uint32_t now_ms) {
  // -- buzzer: bounded duration, then off (non-blocking) -------------------
  if (state_.buzzer_active && (int32_t)(now_ms - state_.buzzer_end_ms) >= 0) {
    stopBuzzer();
  }

  // -- servo: smooth sweep toward the target -------------------------------
  if (state_.servo_current != state_.servo_target &&
      (uint32_t)(now_ms - last_step_ms_) >= SERVO_STEP_INTERVAL_MS) {
    last_step_ms_ = now_ms;
    const int diff = state_.servo_target - state_.servo_current;
    int step = diff;
    if (step > SERVO_STEP_DEGREES) step = SERVO_STEP_DEGREES;
    if (step < -SERVO_STEP_DEGREES) step = -SERVO_STEP_DEGREES;
    state_.servo_current += step;
    if (state_.servo_current < SERVO_MIN_DEGREES) state_.servo_current = SERVO_MIN_DEGREES;
    if (state_.servo_current > SERVO_MAX_DEGREES) state_.servo_current = SERVO_MAX_DEGREES;
#if CONFIG_ENABLE_SERVO
    if (state_.servo_attached) {
      g_servo.write(state_.servo_current);
    }
#endif
  }
}

bool ActuatorManager::applyAction(const Action& action, uint32_t now_ms) {
  const char* result = "applied";

  switch (action.name) {
    case ActionName::SERVO_MOVE:
      setServoTarget(action.angle_degrees);  // clamped
      break;

    case ActionName::BUZZER_BEEP:
      startBuzzer(action.duration_ms, now_ms);  // clamped
      break;

    case ActionName::SET_STATUS_LED:
      if (action.color == LedColor::UNKNOWN) {
        result = "invalid_color";
        break;
      }
      writeLed(action.color);
      break;

    case ActionName::NO_OP:
      result = "no_op";
      break;

    case ActionName::UNKNOWN:
    default:
      result = "rejected";
      strlcpy(state_.last_result, result, sizeof(state_.last_result));
      return false;
  }

  state_.last_action_ms = now_ms;
  strlcpy(state_.last_action, actionNameToString(action.name),
          sizeof(state_.last_action));
  strlcpy(state_.last_result, result, sizeof(state_.last_result));
  return true;
}

void ActuatorManager::safeState(uint32_t now_ms) {
  stopBuzzer();
  writeLed(LedColor::OFF);
  // Servo intentionally HOLDS its current position (see header rationale).
  (void)now_ms;
}
