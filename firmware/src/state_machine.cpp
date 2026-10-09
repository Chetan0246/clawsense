// ===========================================================================
// System state machine implementation.
//
// The transition table below is the single source of truth for what the
// firmware will accept.  Illegal transitions are refused, never coerced.
// ===========================================================================

#include "state_machine.h"

const char* systemStateToString(SystemState state) {
  switch (state) {
    case SystemState::ONLINE_AGENT: return "ONLINE_AGENT";
    case SystemState::DEGRADED:     return "DEGRADED";
    case SystemState::OFFLINE_LOCAL:return "OFFLINE_LOCAL";
    case SystemState::RECOVERY:     return "RECOVERY";
    case SystemState::SAFE_LOCKDOWN:return "SAFE_LOCKDOWN";
  }
  return "UNKNOWN";
}

const char* controllerAuthorityToString(ControllerAuthority authority) {
  return (authority == ControllerAuthority::AGENT) ? "agent" : "local";
}

// -- explicit allowed-transition table --------------------------------------
bool StateMachine::isTransitionAllowed(SystemState from, SystemState to) {
  if (from == to) {
    return true;  // idempotent no-op
  }
  // A critical fault may move any operational state into lockdown.
  if (to == SystemState::SAFE_LOCKDOWN && from != SystemState::SAFE_LOCKDOWN) {
    return true;
  }
  switch (from) {
    case SystemState::ONLINE_AGENT:
      return to == SystemState::DEGRADED;
    case SystemState::DEGRADED:
      return to == SystemState::ONLINE_AGENT || to == SystemState::OFFLINE_LOCAL;
    case SystemState::OFFLINE_LOCAL:
      return to == SystemState::DEGRADED || to == SystemState::RECOVERY;
    case SystemState::RECOVERY:
      return to == SystemState::ONLINE_AGENT || to == SystemState::DEGRADED ||
             to == SystemState::OFFLINE_LOCAL;
    case SystemState::SAFE_LOCKDOWN:
      // Only clearLockdown() may leave lockdown (reset policy).
      return false;
  }
  return false;
}

void StateMachine::begin(uint32_t now_ms) {
  state_ = SystemState::ONLINE_AGENT;
  previous_state_ = SystemState::ONLINE_AGENT;
  authority_ = ControllerAuthority::AGENT;
  last_contact_ms_ = now_ms;
  last_transition_ms_ = now_ms;
  recovery_started_ms_ = 0;
  recovery_checks_ = 0;
  lockdown_fault_cleared_ = false;
  strlcpy(last_reason_, "boot", sizeof(last_reason_));
}

bool StateMachine::requestTransition(SystemState target, const char* reason,
                                     uint32_t now_ms) {
  if (target == state_) {
    return true;  // already there; nothing to log
  }
  if (!isTransitionAllowed(state_, target)) {
    CS_LOGW("state transition REFUSED: %s -> %s (%s)",
            systemStateToString(state_), systemStateToString(target),
            reason ? reason : "");
    return false;
  }
  previous_state_ = state_;
  state_ = target;
  last_transition_ms_ = now_ms;
  strlcpy(last_reason_, reason ? reason : "", sizeof(last_reason_));
  authority_ = (target == SystemState::ONLINE_AGENT ||
                target == SystemState::DEGRADED)
                   ? ControllerAuthority::AGENT
                   : ControllerAuthority::LOCAL;
  CS_LOGI("state %s -> %s (%s)", systemStateToString(previous_state_),
          systemStateToString(state_), last_reason_);
  return true;
}

void StateMachine::notifyBackendContact(uint32_t now_ms) {
  last_contact_ms_ = now_ms;
}

void StateMachine::notifyBackendFailure(uint32_t /*now_ms*/) {
  // Age-based degradation already covers a single failed request.  We do NOT
  // immediately degrade on one failure: that would flap on transient errors.
}

void StateMachine::notifyHealthCheck(bool ok, uint32_t now_ms) {
  if (state_ != SystemState::RECOVERY) {
    return;
  }
  if (ok) {
    ++recovery_checks_;
  } else {
    recovery_checks_ = 0;
    requestTransition(SystemState::DEGRADED, "recovery health check failed",
                      now_ms);
  }
}

void StateMachine::update(uint32_t now_ms) {
  if (state_ == SystemState::SAFE_LOCKDOWN) {
    return;  // requires explicit reset
  }

  const uint32_t age = (uint32_t)(now_ms - last_contact_ms_);

  if (age <= DEGRADED_TIMEOUT_MS) {
    if (state_ == SystemState::RECOVERY) {
      if (recovery_checks_ >= RECOVERY_HEALTH_CHECKS &&
          (uint32_t)(now_ms - recovery_started_ms_) >= RECOVERY_CONFIRM_MS) {
        requestTransition(SystemState::ONLINE_AGENT,
                          "recovery health checks passed", now_ms);
      }
    } else if (state_ == SystemState::OFFLINE_LOCAL) {
      recovery_started_ms_ = now_ms;
      recovery_checks_ = 0;
      requestTransition(SystemState::RECOVERY, "backend contact restored",
                        now_ms);
    } else if (state_ == SystemState::DEGRADED) {
      // The agent is reachable again after a short degradation.  Mirrors the
      // backend, which recovers DEGRADED -> ONLINE_AGENT directly.  Routing
      // this through RECOVERY is not in the transition table, so it would be
      // refused on every loop and leave the node stuck in DEGRADED.
      requestTransition(SystemState::ONLINE_AGENT, "backend contact restored",
                        now_ms);
    }
    return;
  }

  if (age <= OFFLINE_TIMEOUT_MS) {
    if (state_ == SystemState::ONLINE_AGENT ||
        state_ == SystemState::RECOVERY) {
      requestTransition(SystemState::DEGRADED, "backend contact timeout",
                        now_ms);
    }
    return;
  }

  // Beyond the offline timeout: no reliance on the agent at all.
  if (state_ != SystemState::OFFLINE_LOCAL) {
    requestTransition(SystemState::OFFLINE_LOCAL, "backend unreachable", now_ms);
  }
}

void StateMachine::forceLockdown(const char* reason, uint32_t now_ms) {
  lockdown_fault_cleared_ = false;
  requestTransition(SystemState::SAFE_LOCKDOWN, reason, now_ms);
}

void StateMachine::clearLockdown(const char* reason, uint32_t now_ms) {
  if (state_ != SystemState::SAFE_LOCKDOWN) {
    return;
  }
  // Explicit reset policy: fault must be declared cleared by the caller.
  // We re-enter through RECOVERY, never straight to ONLINE_AGENT.
  lockdown_fault_cleared_ = true;
  previous_state_ = state_;
  state_ = SystemState::RECOVERY;
  authority_ = ControllerAuthority::LOCAL;
  recovery_started_ms_ = now_ms;
  recovery_checks_ = 0;
  last_transition_ms_ = now_ms;
  strlcpy(last_reason_, reason ? reason : "lockdown cleared", sizeof(last_reason_));
  CS_LOGI("lockdown cleared -> RECOVERY (%s)", last_reason_);
}

ControllerAuthority StateMachine::authority() const {
  return (state_ == SystemState::ONLINE_AGENT || state_ == SystemState::DEGRADED)
             ? ControllerAuthority::AGENT
             : ControllerAuthority::LOCAL;
}

bool StateMachine::shouldRunLocalController() const {
  return state_ == SystemState::OFFLINE_LOCAL || state_ == SystemState::RECOVERY;
}

bool StateMachine::sourceAllowed(const char* source) const {
  if (source == nullptr || source[0] == '\0') {
    source = "agent";
  }
  switch (state_) {
    case SystemState::ONLINE_AGENT:
    case SystemState::DEGRADED:
      return strcmp(source, "agent") == 0 || strcmp(source, "fallback") == 0 ||
             strcmp(source, "operator") == 0 || strcmp(source, "simulator") == 0;
    case SystemState::OFFLINE_LOCAL:
    case SystemState::RECOVERY:
      return strcmp(source, "fallback") == 0 ||
             strcmp(source, "operator") == 0 ||
             strcmp(source, "simulator") == 0;
    case SystemState::SAFE_LOCKDOWN:
      return false;  // nothing may drive actuators
  }
  return false;
}
