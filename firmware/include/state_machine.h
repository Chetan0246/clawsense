#pragma once

// ===========================================================================
// System state machine (PLAN.md 11).
//
// States (must match backend/app/schemas/system.py SystemState):
//   ONLINE_AGENT  agent available; agent proposals may be executed
//   DEGRADED      transient backend/network failure; local safety still active
//   OFFLINE_LOCAL agent cannot be relied upon; only local rules may act
//   RECOVERY      connectivity returned; health checks in progress
//   SAFE_LOCKDOWN serious fault; NO actuator commands are permitted
//
// The transition table is explicit.  requestTransition() REFUSES any illegal
// transition rather than silently coercing state.  The only way out of
// SAFE_LOCKDOWN is an explicit clearLockdown() (reset policy, PLAN.md 11).
// ===========================================================================

#include <Arduino.h>

#include "config.h"

enum class SystemState : uint8_t {
  ONLINE_AGENT,
  DEGRADED,
  OFFLINE_LOCAL,
  RECOVERY,
  SAFE_LOCKDOWN,
};

// Who currently has authority to drive actuators.
enum class ControllerAuthority : uint8_t {
  AGENT,  // backend/agent proposals are accepted
  LOCAL,  // only the on-device fallback controller may act
};

const char* systemStateToString(SystemState state);
const char* controllerAuthorityToString(ControllerAuthority authority);

class StateMachine {
 public:
  void begin(uint32_t now_ms);

  // Advance timeouts / automatic degradation / recovery.  Call regularly.
  void update(uint32_t now_ms);

  // Attempt a transition.  Returns false (and keeps the current state) if the
  // transition is not in the explicit allowed-transition table.
  bool requestTransition(SystemState target, const char* reason, uint32_t now_ms);

  // Record a successful backend interaction (any served request or health OK).
  void notifyBackendContact(uint32_t now_ms);

  // Record a failed backend health check.
  void notifyBackendFailure(uint32_t now_ms);

  // Report the outcome of a recovery health check (used while in RECOVERY).
  void notifyHealthCheck(bool ok, uint32_t now_ms);

  // Enter lockdown from any state (critical fault).  Fails closed.
  void forceLockdown(const char* reason, uint32_t now_ms);

  // Explicit reset policy: only leaves SAFE_LOCKDOWN after the fault is
  // declared cleared by the caller, and then goes through RECOVERY.
  void clearLockdown(const char* reason, uint32_t now_ms);

  SystemState state() const { return state_; }
  SystemState previousState() const { return previous_state_; }
  ControllerAuthority authority() const;
  const char* stateName() const { return systemStateToString(state_); }
  const char* lastReason() const { return last_reason_; }
  uint32_t lastTransitionMs() const { return last_transition_ms_; }
  uint32_t lastContactMs() const { return last_contact_ms_; }

  // True when the local fallback controller should drive outputs.
  bool shouldRunLocalController() const;

  // True when the given origin may drive actuators in the current state.
  // Mirrors backend safety_supervisor._STATE_SOURCE_RULES.
  bool sourceAllowed(const char* source) const;

 private:
  static bool isTransitionAllowed(SystemState from, SystemState to);

  SystemState state_ = SystemState::ONLINE_AGENT;
  SystemState previous_state_ = SystemState::ONLINE_AGENT;
  ControllerAuthority authority_ = ControllerAuthority::AGENT;

  uint32_t last_contact_ms_ = 0;
  uint32_t last_transition_ms_ = 0;
  uint32_t recovery_started_ms_ = 0;
  int recovery_checks_ = 0;
  bool lockdown_fault_cleared_ = false;

  char last_reason_[64] = {0};
};
