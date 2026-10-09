// ===========================================================================
// On-device safety supervisor implementation.
//
// Deterministic: the same inputs and configuration always produce the same
// decision.  Checks are evaluated in the same order as the backend so the two
// boundaries agree, but the firmware is the last word before an actuator moves.
// ===========================================================================

#include "safety_supervisor.h"

// Reason codes — kept identical to the backend strings.
static constexpr char RC_APPROVED[]              = "APPROVED";
static constexpr char RC_SCHEMA_INVALID[]        = "SCHEMA_INVALID";
static constexpr char RC_UNKNOWN_ACTION[]        = "UNKNOWN_ACTION";
static constexpr char RC_INVALID_PARAMETERS[]    = "INVALID_PARAMETERS";
static constexpr char RC_ANGLE_OUT_OF_RANGE[]    = "ANGLE_OUT_OF_RANGE";
static constexpr char RC_DURATION_OUT_OF_RANGE[] = "DURATION_OUT_OF_RANGE";
static constexpr char RC_CONTEXT_MISSING[]       = "CONTEXT_MISSING";
static constexpr char RC_CONTEXT_STALE[]         = "CONTEXT_STALE";
static constexpr char RC_INVALID_SYSTEM_STATE[]  = "INVALID_SYSTEM_STATE";
static constexpr char RC_COOLDOWN_ACTIVE[]       = "COOLDOWN_ACTIVE";
static constexpr char RC_DUPLICATE_COMMAND[]     = "DUPLICATE_COMMAND";

static void setResult(ValidationResult& r, bool approved, const char* code,
                      const char* reason) {
  r.approved = approved;
  strlcpy(r.reason_code, code, sizeof(r.reason_code));
  strlcpy(r.reason, reason, sizeof(r.reason));
}

// Which origins may drive actuators in each state.  This MUST mirror the
// backend's safety_supervisor._STATE_SOURCE_RULES.
static bool sourceAllowedForState(SystemState state, const char* source) {
  if (source == nullptr || source[0] == '\0') {
    source = "agent";
  }
  switch (state) {
    case SystemState::ONLINE_AGENT:
    case SystemState::DEGRADED:
      return strcmp(source, "agent") == 0 || strcmp(source, "fallback") == 0 ||
             strcmp(source, "operator") == 0 ||
             strcmp(source, "simulator") == 0;
    case SystemState::OFFLINE_LOCAL:
    case SystemState::RECOVERY:
      return strcmp(source, "fallback") == 0 ||
             strcmp(source, "operator") == 0 ||
             strcmp(source, "simulator") == 0;
    case SystemState::SAFE_LOCKDOWN:
      return false;  // fail closed: nothing may drive actuators
  }
  return false;
}

void SafetySupervisor::begin() { reset(); }

void SafetySupervisor::reset() {
  recent_head_ = 0;
  for (size_t i = 0; i < MAX_RECENT; ++i) {
    recent_[i] = RecentExecution();
  }
}

bool SafetySupervisor::contextDependent(ActionName name) {
  // Mirrors backend CONTEXT_DEPENDENT_ACTIONS.
  return name == ActionName::SERVO_MOVE || name == ActionName::BUZZER_BEEP;
}

ValidationResult SafetySupervisor::validate(const Action& action,
                                            SystemState state,
                                            uint32_t context_age_ms,
                                            uint32_t now_ms) {
  ValidationResult r;

  // -- 1. allow-list ------------------------------------------------------
  if (!isActionAllowListed(action.name)) {
    setResult(r, false, RC_UNKNOWN_ACTION,
              "Action is not in the firmware allow-list.");
    return r;
  }

  // -- 2. parameter types / values ----------------------------------------
  if (action.name == ActionName::SET_STATUS_LED &&
      !isLedColorAllowListed(action.color)) {
    setResult(r, false, RC_INVALID_PARAMETERS, "Invalid LED colour.");
    return r;
  }

  // -- 3. numeric ranges --------------------------------------------------
  if (action.name == ActionName::SERVO_MOVE) {
    if (action.angle_degrees < SERVO_MIN_DEGREES ||
        action.angle_degrees > SERVO_MAX_DEGREES) {
      char msg[160];
      snprintf(msg, sizeof(msg),
               "Servo angle %d outside allowed %d-%d degrees.",
               action.angle_degrees, SERVO_MIN_DEGREES, SERVO_MAX_DEGREES);
      setResult(r, false, RC_ANGLE_OUT_OF_RANGE, msg);
      return r;
    }
  }
  if (action.name == ActionName::BUZZER_BEEP) {
    if (action.duration_ms < BUZZER_MIN_MS ||
        action.duration_ms > BUZZER_MAX_MS) {
      char msg[160];
      snprintf(msg, sizeof(msg),
               "Buzzer duration %dms outside allowed %d-%dms.",
               action.duration_ms, BUZZER_MIN_MS, BUZZER_MAX_MS);
      setResult(r, false, RC_DURATION_OUT_OF_RANGE, msg);
      return r;
    }
  }

  // -- 4. context freshness ----------------------------------------------
  if (contextDependent(action.name)) {
    if (context_age_ms == UINT32_MAX) {
      setResult(r, false, RC_CONTEXT_MISSING,
                "No sensor context available; failing closed.");
      return r;
    }
    if (context_age_ms > CONTEXT_MAX_AGE_MS) {
      char msg[160];
      snprintf(msg, sizeof(msg),
               "Context age %lums exceeds maximum %lums.",
               (unsigned long)context_age_ms, (unsigned long)CONTEXT_MAX_AGE_MS);
      setResult(r, false, RC_CONTEXT_STALE, msg);
      return r;
    }
  }

  // -- 5. system state / source ------------------------------------------
  if (!sourceAllowedForState(state, action.source)) {
    char msg[160];
    snprintf(msg, sizeof(msg), "Source '%s' may not drive actuators in state %s.",
             (action.source[0] ? action.source : "agent"),
             systemStateToString(state));
    setResult(r, false, RC_INVALID_SYSTEM_STATE, msg);
    return r;
  }

  // -- 6. cooldown --------------------------------------------------------
  if (action.name != ActionName::NO_OP) {
    uint32_t last_ts = 0;
    if (cooldownActive(action.name, now_ms, &last_ts)) {
      char msg[160];
      snprintf(msg, sizeof(msg), "Cooldown active for '%s' (%ums < %lums).",
               actionNameToString(action.name),
               (unsigned)(uint32_t)(now_ms - last_ts),
               (unsigned long)ACTION_COOLDOWN_MS);
      setResult(r, false, RC_COOLDOWN_ACTIVE, msg);
      return r;
    }
  }

  // -- 7. duplicate -------------------------------------------------------
  if (findDuplicate(action, now_ms)) {
    char msg[160];
    snprintf(msg, sizeof(msg),
             "Identical '%s' command already executed within %lums.",
             actionNameToString(action.name), (unsigned long)ACTION_COOLDOWN_MS);
    setResult(r, false, RC_DUPLICATE_COMMAND, msg);
    return r;
  }

  setResult(r, true, RC_APPROVED, "All firmware safety checks passed.");
  return r;
}

ValidationResult SafetySupervisor::validateRaw(const char* body, Action& out,
                                               SystemState state,
                                               uint32_t context_age_ms,
                                               uint32_t now_ms) {
  ValidationResult r;
  out = Action();

  const char* err_code = RC_SCHEMA_INVALID;
  const char* err_detail = "Malformed JSON.";
  if (!parseActionJson(body, out, &err_code, &err_detail)) {
    setResult(r, false, err_code, err_detail);
    return r;
  }

  // Default origin is the backend/agent when the field is absent.
  if (out.source[0] == '\0') {
    strlcpy(out.source, "agent", sizeof(out.source));
  }

  return validate(out, state, context_age_ms, now_ms);
}

void SafetySupervisor::recordExecution(const Action& action, uint32_t now_ms) {
  RecentExecution& slot = recent_[recent_head_];
  slot.name = action.name;
  slot.angle = action.angle_degrees;
  slot.duration = action.duration_ms;
  slot.color = action.color;
  slot.ts = now_ms;
  slot.used = true;
  recent_head_ = (recent_head_ + 1) % MAX_RECENT;
}

bool SafetySupervisor::cooldownActive(ActionName name, uint32_t now_ms,
                                      uint32_t* out_ts) const {
  uint32_t newest = 0;
  bool found = false;
  for (size_t i = 0; i < MAX_RECENT; ++i) {
    const RecentExecution& e = recent_[i];
    if (!e.used || e.name != name) {
      continue;
    }
    if ((uint32_t)(now_ms - e.ts) <= ACTION_COOLDOWN_MS) {
      if (!found || e.ts > newest) {
        newest = e.ts;
        found = true;
      }
    }
  }
  if (found && out_ts != nullptr) {
    *out_ts = newest;
  }
  return found;
}

bool SafetySupervisor::findDuplicate(const Action& action,
                                     uint32_t now_ms) const {
  for (size_t i = 0; i < MAX_RECENT; ++i) {
    const RecentExecution& e = recent_[i];
    if (!e.used || e.name != action.name) {
      continue;
    }
    if ((uint32_t)(now_ms - e.ts) > ACTION_COOLDOWN_MS) {
      continue;
    }
    if (action.name == ActionName::SERVO_MOVE && e.angle == action.angle_degrees) {
      return true;
    }
    if (action.name == ActionName::BUZZER_BEEP && e.duration == action.duration_ms) {
      return true;
    }
    if (action.name == ActionName::SET_STATUS_LED && e.color == action.color) {
      return true;
    }
    if (action.name == ActionName::NO_OP) {
      return true;
    }
  }
  return false;
}
