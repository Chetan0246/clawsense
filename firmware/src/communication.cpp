// ===========================================================================
// Communication manager implementation.
//
// Never blocks the control loop: WiFi is driven by a small non-blocking state
// machine and the HTTP server's handleClient() returns immediately when idle.
// ===========================================================================

#include "communication.h"

#include <ArduinoJson.h>
#include <WiFi.h>
#include <math.h>
#include <time.h>

const char* wifiStateToString(WifiState state) {
  switch (state) {
    case WifiState::DISABLED:     return "disabled";
    case WifiState::DISCONNECTED: return "disconnected";
    case WifiState::CONNECTING:   return "connecting";
    case WifiState::CONNECTED:    return "connected";
  }
  return "unknown";
}

void Communication::begin(SensorManager* sensors, StateMachine* state_machine,
                          SafetySupervisor* safety, ActuatorManager* actuators,
                          ContextBuffer* context, EventEngine* events) {
  sensors_ = sensors;
  state_machine_ = state_machine;
  safety_ = safety;
  actuators_ = actuators;
  context_ = context;
  events_ = events;

  if (strlen(WIFI_SSID) == 0) {
    // No credentials committed -> run local-only.  This is a safe, supported
    // mode, not an error: the node still enforces all safety rules locally.
    wifi_state_ = WifiState::DISABLED;
    CS_LOGW("no WiFi credentials configured; running local-only (AP-less)");
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.setHostname(WIFI_HOSTNAME);
  wifi_state_ = WifiState::DISCONNECTED;
  next_retry_ms_ = 0;
  retry_backoff_ms_ = WIFI_RETRY_MIN_MS;
  CS_LOGI("WiFi configured; will connect in background");
}

void Communication::startServer() {
  if (server_started_) {
    return;
  }
  server_.on("/health", HTTP_GET, [this]() { handleHealth(); });
  server_.on("/telemetry", HTTP_GET, [this]() { handleTelemetry(); });
  server_.on("/command", HTTP_POST, [this]() { handleCommand(); });
  server_.onNotFound([this]() { handleNotFound(); });
  server_.enableCORS(true);
  server_.begin();
  server_started_ = true;
  CS_LOGI("HTTP server listening on port %u", (unsigned)CONFIG_HTTP_PORT);
}

void Communication::update(uint32_t now_ms) {
  if (wifi_state_ == WifiState::DISABLED) {
    return;
  }

  const bool link_up = (WiFi.status() == WL_CONNECTED);

  if (link_up) {
    if (wifi_state_ != WifiState::CONNECTED) {
      wifi_state_ = WifiState::CONNECTED;
      ever_connected_ = true;
      retry_backoff_ms_ = WIFI_RETRY_MIN_MS;
      // Log the IP only — NEVER the credentials.
      CS_LOGI("WiFi connected, ip=%s", WiFi.localIP().toString().c_str());
      if (!ntp_started_) {
        configTime(0, 0, CONFIG_NTP_SERVER);  // SNTP; non-blocking
        ntp_started_ = true;
      }
      startServer();
    }
  } else {
    if (wifi_state_ == WifiState::CONNECTED) {
      wifi_state_ = WifiState::DISCONNECTED;
      CS_LOGW("WiFi link lost; local safety remains active");
    }

    if (wifi_state_ == WifiState::CONNECTING) {
      if ((uint32_t)(now_ms - connect_started_ms_) >= WIFI_CONNECT_TIMEOUT_MS) {
        wifi_state_ = WifiState::DISCONNECTED;
        next_retry_ms_ = now_ms + retry_backoff_ms_;
      }
    }

    if (wifi_state_ == WifiState::DISCONNECTED &&
        (int32_t)(now_ms - next_retry_ms_) >= 0) {
      wifi_state_ = WifiState::CONNECTING;
      connect_started_ms_ = now_ms;
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      retry_backoff_ms_ = min(retry_backoff_ms_ * 2, WIFI_RETRY_MAX_MS);
      CS_LOGI("WiFi connect attempt (next backoff up to %lums)",
              (unsigned long)retry_backoff_ms_);
    }
  }

  if (server_started_) {
    server_.handleClient();
  }
}

bool Communication::timeSynced() const {
  return time(nullptr) > CONFIG_TIME_VALID_AFTER;
}

uint64_t Communication::epochMs() const {
  const time_t t = time(nullptr);
  if (t > CONFIG_TIME_VALID_AFTER) {
    return (uint64_t)t * 1000ULL;
  }
  // Honest fallback: we have no RTC/NTP, so report monotonic uptime instead of
  // inventing an epoch.  Documented limitation (README).
  return (uint64_t)millis();
}

// -- HTTP handlers ----------------------------------------------------------

void Communication::handleHealth() {
  const uint32_t now = millis();
  if (state_machine_ != nullptr) {
    state_machine_->notifyBackendContact(now);
    if (state_machine_->state() == SystemState::RECOVERY) {
      state_machine_->notifyHealthCheck(true, now);
    }
  }

  JsonDocument doc;
  doc["status"] = "ok";
  doc["firmware"] = FIRMWARE_VERSION;
  doc["device_id"] = DEVICE_ID;
  doc["state"] = (state_machine_ != nullptr) ? state_machine_->stateName() : "UNKNOWN";
  doc["controller"] = (state_machine_ != nullptr)
                          ? controllerAuthorityToString(state_machine_->authority())
                          : "unknown";
  doc["uptime_ms"] = now;

  String out;
  serializeJson(doc, out);
  server_.send(200, "application/json", out);
}

void Communication::buildTelemetryJson(JsonDocument& doc) const {
  doc["device_id"] = DEVICE_ID;
  doc["timestamp"] = epochMs();
  doc["simulated"] = false;  // real hardware readings only

  JsonObject readings = doc["readings"].to<JsonObject>();
  if (sensors_ == nullptr) {
    return;
  }
  const SensorSnapshot& s = sensors_->snapshot();

  auto addScalar = [&](const char* name, const SensorValue& v) {
    JsonObject o = readings[name].to<JsonObject>();
    o["unit"] = v.unit;
    o["status"] = sensorStatusToString(v.status);
    if (v.valid) {
      o["value"] = v.value;
    } else {
      o["value"] = nullptr;  // never coerce a missing value to 0
    }
  };
  addScalar("temperature_c", s.temperature);
  addScalar("humidity_percent", s.humidity);
  addScalar("light_lux", s.light);

  JsonObject motion = readings["motion"].to<JsonObject>();
  motion["unit"] = "bool";
  motion["status"] = sensorStatusToString(s.motion_status);
  if (s.motion_valid) {
    motion["value"] = s.motion;
  } else {
    motion["value"] = nullptr;
  }
}

void Communication::handleTelemetry() {
  const uint32_t now = millis();
  if (state_machine_ != nullptr) {
    state_machine_->notifyBackendContact(now);
  }
  JsonDocument doc;
  buildTelemetryJson(doc);
  String out;
  serializeJson(doc, out);
  server_.send(200, "application/json", out);
}

void Communication::buildReportedState(JsonObject out) const {
  if (actuators_ == nullptr) {
    return;
  }
  const ActuatorState& a = actuators_->state();
  out["servo_angle"] = a.servo_current;
  out["servo_target"] = a.servo_target;
  out["servo_moving"] = (a.servo_current != a.servo_target);
  out["buzzer_active"] = a.buzzer_active;
  out["led"] = ledColorToString(a.led);
  out["state"] = (state_machine_ != nullptr) ? state_machine_->stateName() : "UNKNOWN";
  out["controller"] = (state_machine_ != nullptr)
                          ? controllerAuthorityToString(state_machine_->authority())
                          : "unknown";
}

void Communication::handleCommand() {
  const uint32_t now = millis();
  if (state_machine_ != nullptr) {
    state_machine_->notifyBackendContact(now);
  }

  const String body = server_.arg("plain");

  Action action;
  const uint32_t context_age_ms =
      (context_ != nullptr) ? context_->latestAgeMs(now) : UINT32_MAX;
  const SystemState st =
      (state_machine_ != nullptr) ? state_machine_->state() : SystemState::SAFE_LOCKDOWN;

  ValidationResult vr;
  if (safety_ != nullptr) {
    vr = safety_->validateRaw(body.c_str(), action, st, context_age_ms, now);
  } else {
    strlcpy(vr.reason_code, "INTERNAL_ERROR", sizeof(vr.reason_code));
    strlcpy(vr.reason, "Safety supervisor unavailable; failing closed.",
            sizeof(vr.reason));
    vr.approved = false;
  }

  bool applied = false;
  if (vr.approved && actuators_ != nullptr) {
    applied = actuators_->applyAction(action, now);
    if (applied && safety_ != nullptr) {
      safety_->recordExecution(action, now);
    }
  }

  const bool ack = vr.approved && applied;

  // Record the outcome for the OLED + audit trail.
  strlcpy(last_command_action_, actionNameToString(action.name),
          sizeof(last_command_action_));
  strlcpy(last_command_detail_, ack ? "executed" : vr.reason_code,
          sizeof(last_command_detail_));

  if (events_ != nullptr && context_ != nullptr) {
    if (ack) {
      events_->emit(EventType::ACTION_APPROVED, NAN, actionNameToString(action.name),
                    now, *context_);
      events_->emit(EventType::COMMAND_ACKNOWLEDGED, NAN, actionNameToString(action.name),
                    now, *context_);
    } else {
      events_->emit(EventType::ACTION_REJECTED, NAN, vr.reason_code, now, *context_);
      events_->emit(EventType::COMMAND_REJECTED, NAN, vr.reason_code, now, *context_);
    }
  }

  JsonDocument doc;
  doc["acknowledged"] = ack;
  doc["state_confirmed"] = ack;
  doc["detail"] = ack ? "Command executed and state confirmed." : vr.reason;
  doc["reason_code"] = vr.reason_code;
  if (action.has_command_id) {
    doc["command_id"] = action.command_id;  // echo correlation id
  }

  JsonObject reported = doc["reported_state"].to<JsonObject>();
  if (ack) {
    buildReportedState(reported);
  }
  // On rejection reported_state stays an empty object ({}).

  String out;
  serializeJson(doc, out);
  // Rejections are a structured 200 response: the backend must be able to read
  // acknowledged=false, and a non-2xx would be treated as a transport error.
  server_.send(200, "application/json", out);

  if (ack) {
    CS_LOGI("command '%s' executed", last_command_action_);
  } else {
    CS_LOGW("command '%s' rejected: %s (%s)", last_command_action_,
            vr.reason_code, vr.reason);
  }
}

void Communication::handleNotFound() {
  JsonDocument doc;
  doc["status"] = "not_found";
  doc["detail"] = "Unknown endpoint.";
  String out;
  serializeJson(doc, out);
  server_.send(404, "application/json", out);
}
