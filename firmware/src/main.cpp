// ===========================================================================
// ClawSense ESP32-S3 firmware entry point (PLAN.md 14, 21).
//
// loop() is fully non-blocking and millis()-scheduled.  Every subsystem is
// advanced by a bounded amount of work each pass, so no single sensor read,
// network call, display refresh or actuator step can stall the control loop.
//
// Execution order matters:
//   1. outputs are initialised to their SAFE STATE before anything else;
//   2. sensors are sampled and validated;
//   3. events/context are updated from the new sample;
//   4. the state machine evaluates timeouts/degradation/recovery;
//   5. the local fallback controller runs when the agent is not authoritative;
//   6. actuators are advanced (smooth servo sweep, bounded buzzer);
//   7. the HTTP server is serviced (non-blocking);
//   8. the OLED is refreshed (throttled).
//
// Safety is enforced independently at every step: the local controller's
// output is re-validated by the on-device safety supervisor, exactly like a
// backend command.  Nothing bypasses validation.
// ===========================================================================

#include <Arduino.h>
#include <math.h>

#include "actuator_manager.h"
#include "buttons.h"
#include "communication.h"
#include "config.h"
#include "context_buffer.h"
#include "display.h"
#include "event_engine.h"
#include "local_controller.h"
#include "safety_supervisor.h"
#include "sensor_manager.h"
#include "state_machine.h"

// -- module instances -------------------------------------------------------
static SensorManager     g_sensors;
static EventEngine       g_events;
static ContextBuffer     g_context;
static SafetySupervisor  g_safety;
static StateMachine      g_state;
static LocalController   g_local;
static ActuatorManager   g_actuators;
static Display           g_display;
static Communication     g_comms;
static Buttons           g_buttons;

// -- loop-local bookkeeping -------------------------------------------------
static bool g_local_active = false;

// Status-LED colour for the current system state (PLAN.md 14):
//   green  = ONLINE_AGENT
//   yellow = DEGRADED / RECOVERY
//   red    = OFFLINE_LOCAL / SAFE_LOCKDOWN (fault)
// The LED is re-asserted on every state transition; an explicit set_status_led
// action may override it until the next transition.
static LedColor stateLedColor(SystemState state) {
  switch (state) {
    case SystemState::ONLINE_AGENT:  return LedColor::GREEN;
    case SystemState::DEGRADED:
    case SystemState::RECOVERY:      return LedColor::YELLOW;
    case SystemState::OFFLINE_LOCAL:
    case SystemState::SAFE_LOCKDOWN: return LedColor::RED;
  }
  return LedColor::RED;
}

static SystemState g_last_led_state = SystemState::ONLINE_AGENT;
static bool        g_led_state_initialised = false;

// Runtime guard mirroring the compile-time static_asserts in config.h.  It can
// never fire with a valid build, but keeps the SAFE_LOCKDOWN path explicit.
static bool safetyConfigValid() {
  return SERVO_MIN_DEGREES < SERVO_MAX_DEGREES &&
         SERVO_MAX_DEGREES <= 180 &&
         BUZZER_MIN_MS >= 1 && BUZZER_MIN_MS < BUZZER_MAX_MS &&
         TEMP_LOW_C < TEMP_HIGH_C;
}

void setup() {
  Serial.begin(115200);
  delay(50);  // allow native-USB CDC to enumerate; setup only, never in loop()

  CS_LOGI("ClawSense firmware %s", FIRMWARE_VERSION);
  CS_LOGI("device_id=%s board=esp32s3", DEVICE_ID);

  const uint32_t now = millis();

  // 1. Outputs first: guarantee a documented safe state before any input.
  g_actuators.begin();

  // 2. Inputs.
  g_sensors.begin();
  g_sensors.sampleNow(now);
  g_buttons.begin();

  // 3. Context / events / safety / state.
  g_context.begin();
  g_events.begin(now);
  g_safety.begin();
  g_state.begin(now);
  g_local.begin();

  // 4. Informative output (never safety-critical).
  g_display.begin();

  // 5. Communication last: it may take time to associate and must not delay
  //    local safety from becoming active.
  g_comms.begin(&g_sensors, &g_state, &g_safety, &g_actuators, &g_context,
                &g_events);

  g_context.setLatestReadings(g_sensors.snapshot(), now);
  g_events.emit(EventType::BOOT, NAN, "firmware boot", now, g_context);

  if (!safetyConfigValid()) {
    g_state.forceLockdown("invalid safety configuration", now);
  }

  CS_LOGI("setup complete; state=%s", g_state.stateName());
}

void loop() {
  const uint32_t now = millis();

  // -- 0. operator buttons: LOCAL, non-actuator effects only --------------
  // A press only sets a one-shot flag.  Button 2 asks for a sensor re-read;
  // button 1 records an operator acknowledgement.  Neither drives an actuator
  // nor bypasses the on-device safety supervisor.
  g_buttons.update(now);
  if (g_buttons.consumeReread()) {
    g_sensors.requestImmediateSample();
    g_events.emit(EventType::SENSOR_REREAD_REQUESTED, NAN,
                  "button: sensor re-read requested", now, g_context);
  }
  if (g_buttons.consumeAck()) {
    g_events.emit(EventType::BUTTON_ACK, NAN, "button: operator acknowledge",
                  now, g_context);
    CS_LOGI("operator acknowledge button pressed (local event only)");
  }

  // -- 1. sensors: interval-driven, non-blocking --------------------------
  const uint32_t before_ts = g_sensors.snapshot().timestamp_ms;
  g_sensors.update(now);
  const SensorSnapshot& snap = g_sensors.snapshot();
  if (snap.timestamp_ms != before_ts) {
    // A new sample is available: refresh context and evaluate events.
    g_context.setLatestReadings(snap, now);
    g_events.update(snap, now, g_context);
  }

  // -- 2. state machine: timeouts, degradation, recovery ------------------
  g_state.update(now);

  // Reflect the state on the discrete status LEDs, but only on a transition so
  // an explicit set_status_led action is not immediately overridden.
  if (!g_led_state_initialised || g_state.state() != g_last_led_state) {
    g_led_state_initialised = true;
    g_last_led_state = g_state.state();
    g_actuators.setStatusLed(stateLedColor(g_last_led_state));
  }

  // -- 3. local fallback controller (agent unavailable) -------------------
  if (g_state.shouldRunLocalController()) {
    if (!g_local_active) {
      g_local_active = true;
      g_events.emit(EventType::FALLBACK_ACTIVATED, NAN,
                    g_state.lastReason(), now, g_context);
      CS_LOGW("local fallback active (%s)", g_state.lastReason());
    }

    LocalDecision decision;
    if (g_local.evaluate(snap, now, decision)) {
      for (size_t i = 0; i < decision.count; ++i) {
        Action action = decision.actions[i];
        // The fallback output is validated by the SAME supervisor as any
        // backend command — local does not mean unvalidated.
        ValidationResult vr = g_safety.validate(
            action, g_state.state(), g_context.latestAgeMs(now), now);
        if (vr.approved) {
          if (g_actuators.applyAction(action, now)) {
            g_safety.recordExecution(action, now);
          }
        } else {
          g_events.emit(EventType::ACTION_REJECTED, NAN, vr.reason_code, now,
                        g_context);
        }
      }
    }
  } else {
    g_local_active = false;
  }

  // -- 4. actuators: smooth sweep + bounded buzzer ------------------------
  g_actuators.update(now);

  // -- 5. communication: WiFi + HTTP server (non-blocking) ----------------
  g_comms.update(now);

  // -- 6. display: throttled, purely informative --------------------------
  g_display.update(now, g_state.state(), g_state.authority(), snap,
                   g_comms.wifiState(), g_comms.lastCommandAction(),
                   g_comms.lastCommandDetail());

  // Watchdog-friendly scheduler yield.  This is NOT a control delay: it hands
  // the CPU to the WiFi/idle tasks so the task watchdog is fed and the radio
  // stays responsive, then returns immediately.
  yield();
}
