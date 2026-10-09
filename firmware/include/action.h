#pragma once

// ===========================================================================
// Structured action contract (PLAN.md section 9).
//
// Mirrors backend/app/schemas/actions.py exactly:
//   ActionName : servo_move | buzzer_beep | set_status_led | no_op
//   LedColor   : green | yellow | red | off
//
// The firmware treats every incoming action as an UNTRUSTED proposal.  This
// header only *describes* and *parses* actions; it never decides whether an
// action is safe.  That decision belongs to safety_supervisor.
//
// Implemented header-only so the module has no separate translation unit.
// ===========================================================================

#include <Arduino.h>
#include <ArduinoJson.h>
#include <string.h>

#include "config.h"

// Allow-listed action names (backend ActionName enum).
enum class ActionName : uint8_t {
  SERVO_MOVE,
  BUZZER_BEEP,
  SET_STATUS_LED,
  NO_OP,
  UNKNOWN,  // never allow-listed; used for anything unrecognised
};

// Allow-listed LED colours (backend LedColor enum).
enum class LedColor : uint8_t {
  GREEN,
  YELLOW,
  RED,
  OFF,
  UNKNOWN,  // invalid; rejected by the supervisor
};

// A parsed action proposal.  Numeric fields default to 0 and are only
// meaningful when the matching action name is selected; the supervisor
// validates their ranges before execution.
struct Action {
  ActionName name = ActionName::UNKNOWN;
  int angle_degrees = 0;           // servo_move
  int duration_ms = 0;             // buzzer_beep
  LedColor color = LedColor::OFF;  // set_status_led

  // Optional command correlation id echoed back to the backend.
  bool has_command_id = false;
  char command_id[CONFIG_COMMAND_ID_MAX_LEN] = {0};

  // Origin of the action: "agent" (backend), "fallback" (local), "operator".
  char source[CONFIG_SOURCE_MAX_LEN] = {0};

  // Optional bounded explanation, for audit only.
  char reason[CONFIG_DETAIL_MAX_LEN * 2] = {0};
};

// -- name <-> string --------------------------------------------------------
inline const char* actionNameToString(ActionName name) {
  switch (name) {
    case ActionName::SERVO_MOVE:     return "servo_move";
    case ActionName::BUZZER_BEEP:    return "buzzer_beep";
    case ActionName::SET_STATUS_LED: return "set_status_led";
    case ActionName::NO_OP:          return "no_op";
    case ActionName::UNKNOWN:        return "unknown";
  }
  return "unknown";
}

inline ActionName actionNameFromString(const char* value) {
  if (value == nullptr) return ActionName::UNKNOWN;
  if (strcmp(value, "servo_move") == 0)     return ActionName::SERVO_MOVE;
  if (strcmp(value, "buzzer_beep") == 0)    return ActionName::BUZZER_BEEP;
  if (strcmp(value, "set_status_led") == 0) return ActionName::SET_STATUS_LED;
  if (strcmp(value, "no_op") == 0)          return ActionName::NO_OP;
  return ActionName::UNKNOWN;
}

inline const char* ledColorToString(LedColor color) {
  switch (color) {
    case LedColor::GREEN:   return "green";
    case LedColor::YELLOW:  return "yellow";
    case LedColor::RED:     return "red";
    case LedColor::OFF:     return "off";
    case LedColor::UNKNOWN: return "unknown";
  }
  return "unknown";
}

inline LedColor ledColorFromString(const char* value) {
  if (value == nullptr) return LedColor::UNKNOWN;
  if (strcmp(value, "green") == 0)  return LedColor::GREEN;
  if (strcmp(value, "yellow") == 0) return LedColor::YELLOW;
  if (strcmp(value, "red") == 0)    return LedColor::RED;
  if (strcmp(value, "off") == 0)    return LedColor::OFF;
  return LedColor::UNKNOWN;
}

// True when `name` is one of the four allow-listed actions.
inline bool isActionAllowListed(ActionName name) {
  return name == ActionName::SERVO_MOVE || name == ActionName::BUZZER_BEEP ||
         name == ActionName::SET_STATUS_LED || name == ActionName::NO_OP;
}

// True when `color` is one of the four allow-listed colours.
inline bool isLedColorAllowListed(LedColor color) {
  return color == LedColor::GREEN || color == LedColor::YELLOW ||
         color == LedColor::RED || color == LedColor::OFF;
}

// Parse a raw JSON command body into `out`.
//
// Returns true only when the JSON is well-formed AND the mandatory structural
// fields are present with the right types (action string, parameters object,
// and the parameters required by that action).  It does NOT enforce ranges or
// the allow-list — the safety supervisor does that.
//
// On failure `error_code`/`error_detail` describe why (for the audit trail).
inline bool parseActionJson(const char* body, Action& out,
                            const char** error_code, const char** error_detail) {
  *error_code = "SCHEMA_INVALID";
  *error_detail = "Malformed JSON.";

  if (body == nullptr) {
    return false;
  }

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    *error_detail = "Malformed JSON body.";
    return false;
  }
  if (!doc.is<JsonObject>()) {
    *error_detail = "Body is not a JSON object.";
    return false;
  }

  // -- action (required, non-empty string) --------------------------------
  if (!doc["action"].is<const char*>()) {
    *error_detail = "'action' must be a non-empty string.";
    return false;
  }
  const char* action_str = doc["action"].as<const char*>();
  if (action_str == nullptr || action_str[0] == '\0') {
    *error_detail = "'action' must be a non-empty string.";
    return false;
  }
  out.name = actionNameFromString(action_str);

  // -- parameters (required object) ---------------------------------------
  if (!doc["parameters"].is<JsonObject>()) {
    *error_detail = "'parameters' must be an object.";
    return false;
  }
  JsonObject params = doc["parameters"].as<JsonObject>();

  // -- per-action required parameters -------------------------------------
  switch (out.name) {
    case ActionName::SERVO_MOVE:
      if (!params["angle_degrees"].is<int>()) {
        *error_detail = "servo_move requires integer 'angle_degrees'.";
        return false;
      }
      out.angle_degrees = params["angle_degrees"].as<int>();
      break;

    case ActionName::BUZZER_BEEP:
      if (!params["duration_ms"].is<int>()) {
        *error_detail = "buzzer_beep requires integer 'duration_ms'.";
        return false;
      }
      out.duration_ms = params["duration_ms"].as<int>();
      break;

    case ActionName::SET_STATUS_LED:
      if (!params["color"].is<const char*>()) {
        *error_detail = "set_status_led requires string 'color'.";
        return false;
      }
      out.color = ledColorFromString(params["color"].as<const char*>());
      break;

    case ActionName::NO_OP:
      // no parameters required
      break;

    case ActionName::UNKNOWN:
    default:
      // Structural parse succeeded; the allow-list check rejects it later.
      break;
  }

  // -- optional command_id -------------------------------------------------
  if (doc["command_id"].is<const char*>()) {
    const char* cid = doc["command_id"].as<const char*>();
    if (cid != nullptr && cid[0] != '\0') {
      strlcpy(out.command_id, cid, sizeof(out.command_id));
      out.has_command_id = true;
    }
  }

  // -- optional source / reason (audit only) ------------------------------
  if (doc["source"].is<const char*>()) {
    strlcpy(out.source, doc["source"].as<const char*>(), sizeof(out.source));
  }
  if (doc["reason"].is<const char*>()) {
    strlcpy(out.reason, doc["reason"].as<const char*>(), sizeof(out.reason));
  }

  *error_code = "";
  *error_detail = "";
  return true;
}
