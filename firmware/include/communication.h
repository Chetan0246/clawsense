#pragma once

// ===========================================================================
// Communication manager (PLAN.md 14, 15).
//
// Exposes the HTTP contract the backend expects
// (backend/app/transports/http_transport.py):
//
//   GET  /health   -> 200 {"status":"ok","firmware":"...","state":"..."}
//   GET  /telemetry-> {"device_id":..,"timestamp":<epoch ms>,"simulated":false,
//                      "readings":{...}}
//   POST /command  -> {"acknowledged":bool,"state_confirmed":bool,
//                      "detail":"...","reported_state":{...}}
//
// Design:
//   * WiFi is brought up NON-blocking, with bounded exponential backoff.
//   * If no WiFi credentials are configured the node runs AP-less / local-only
//     (a valid OFFLINE_LOCAL operating mode) — it never blocks or reboots.
//   * The HTTP server is only started once a link exists; handleClient() is
//     non-blocking and returns immediately when idle.
//   * Any successfully served request counts as backend contact, which drives
//     the state machine's recovery logic.
// ===========================================================================

#include <Arduino.h>
#include <ArduinoJson.h>
#include <WebServer.h>

#include "actuator_manager.h"
#include "config.h"
#include "context_buffer.h"
#include "event_engine.h"
#include "safety_supervisor.h"
#include "sensor_manager.h"
#include "state_machine.h"

enum class WifiState : uint8_t {
  DISABLED,      // no credentials configured
  DISCONNECTED,  // credentials present, link down
  CONNECTING,
  CONNECTED,
};

const char* wifiStateToString(WifiState state);

class Communication {
 public:
  void begin(SensorManager* sensors, StateMachine* state_machine,
             SafetySupervisor* safety, ActuatorManager* actuators,
             ContextBuffer* context, EventEngine* events);

  // Non-blocking: maintains WiFi, runs the HTTP server, applies backoff.
  void update(uint32_t now_ms);

  WifiState wifiState() const { return wifi_state_; }
  bool connected() const { return wifi_state_ == WifiState::CONNECTED; }
  bool timeSynced() const;
  uint64_t epochMs() const;

  // Last command summary, for the OLED.
  const char* lastCommandDetail() const { return last_command_detail_; }
  const char* lastCommandAction() const { return last_command_action_; }

 private:
  void startServer();
  void handleHealth();
  void handleTelemetry();
  void handleCommand();
  void handleNotFound();
  void buildTelemetryJson(JsonDocument& doc) const;
  void buildReportedState(JsonObject out) const;

  WebServer server_{CONFIG_HTTP_PORT};
  SensorManager* sensors_ = nullptr;
  StateMachine* state_machine_ = nullptr;
  SafetySupervisor* safety_ = nullptr;
  ActuatorManager* actuators_ = nullptr;
  ContextBuffer* context_ = nullptr;
  EventEngine* events_ = nullptr;

  WifiState wifi_state_ = WifiState::DISABLED;
  bool server_started_ = false;
  bool ever_connected_ = false;
  bool ntp_started_ = false;
  uint32_t next_retry_ms_ = 0;
  uint32_t retry_backoff_ms_ = WIFI_RETRY_MIN_MS;
  uint32_t connect_started_ms_ = 0;

  char last_command_action_[24] = {0};
  char last_command_detail_[96] = {0};
};
