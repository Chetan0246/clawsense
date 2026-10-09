#pragma once

// ===========================================================================
// On-device deterministic safety supervisor (PLAN.md 10, 14).
//
// This is the firmware's INDEPENDENT safety boundary.  It re-validates every
// incoming command even though the backend already validated it: a backend
// approval is NOT proof of physical safety (PLAN.md 10).
//
// It rejects, deterministically and with an explicit reason code:
//   * malformed JSON                     -> SCHEMA_INVALID
//   * unknown / non-allow-listed action  -> UNKNOWN_ACTION
//   * wrong / missing parameter types    -> INVALID_PARAMETERS
//   * servo angle outside 0..180         -> ANGLE_OUT_OF_RANGE
//   * buzzer duration outside 1..2000 ms -> DURATION_OUT_OF_RANGE
//   * invalid LED colour                 -> INVALID_PARAMETERS
//   * missing / stale sensor context     -> CONTEXT_MISSING / CONTEXT_STALE
//   * source not permitted in state      -> INVALID_SYSTEM_STATE
//   * repeated too soon                  -> COOLDOWN_ACTIVE
//   * identical command in window        -> DUPLICATE_COMMAND
//
// Reason codes intentionally match backend/app/services/safety_supervisor.py.
// ===========================================================================

#include <Arduino.h>

#include "action.h"
#include "config.h"
#include "sensor_manager.h"
#include "state_machine.h"

struct ValidationResult {
  bool approved = false;
  char reason_code[32] = "UNKNOWN";
  char reason[160] = "";
};

class SafetySupervisor {
 public:
  void begin();
  void reset();

  // Validate a parsed action.  `context_age_ms` is the age of the latest
  // sensor snapshot in milliseconds, or UINT32_MAX when no snapshot exists
  // (the caller owns the context buffer).  Missing vs stale context produce
  // the same reason codes as the backend (CONTEXT_MISSING / CONTEXT_STALE).
  ValidationResult validate(const Action& action, SystemState state,
                            uint32_t context_age_ms, uint32_t now_ms);

  // Parse + validate a raw JSON command body in one deterministic step.
  // On success `out` holds the parsed action and the result is approved (or
  // rejected for a semantic reason).  On structural failure the result is a
  // schema rejection and `out` must not be executed.
  ValidationResult validateRaw(const char* body, Action& out, SystemState state,
                               uint32_t context_age_ms, uint32_t now_ms);

  // Record a successfully executed action (feeds cooldown + duplicate checks).
  void recordExecution(const Action& action, uint32_t now_ms);

 private:
  struct RecentExecution {
    ActionName name = ActionName::UNKNOWN;
    int angle = 0;
    int duration = 0;
    LedColor color = LedColor::OFF;
    uint32_t ts = 0;
    bool used = false;
  };

  static constexpr size_t MAX_RECENT = 16;

  // Returns true and sets `out_ts` when `name` ran within the cooldown window.
  bool cooldownActive(ActionName name, uint32_t now_ms, uint32_t* out_ts) const;
  bool findDuplicate(const Action& action, uint32_t now_ms) const;
  static bool contextDependent(ActionName name);

  RecentExecution recent_[MAX_RECENT];
  size_t recent_head_ = 0;
};
