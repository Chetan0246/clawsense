#pragma once

// ===========================================================================
// OLED display manager (PLAN.md 14).
//
// A 128x64 SSD1306 I2C panel at address 0x3C showing:
//   * system state + controller authority
//   * latest sensor values (or a status when a sensor is not OK)
//   * WiFi / backend connection status
//   * last command and its result
//
// Degrades gracefully: if the panel is absent or fails to initialise, the
// firmware logs it once and continues with every other subsystem intact.
// ===========================================================================

#include <Adafruit_SSD1306.h>
#include <Adafruit_GFX.h>
#include <Arduino.h>
#include <Wire.h>

#include "communication.h"  // WifiState
#include "config.h"
#include "sensor_manager.h"
#include "state_machine.h"

class Display {
 public:
  Display();

  // Returns true when the panel is present and usable.
  bool begin();

  // Non-blocking; internally throttled to DISPLAY_REFRESH_INTERVAL_MS.
  void update(uint32_t now_ms, SystemState state, ControllerAuthority authority,
              const SensorSnapshot& sensors, WifiState wifi,
              const char* last_cmd_action, const char* last_cmd_detail);

 private:
  static void formatScalar(const SensorValue& v, char* out, size_t len);

  Adafruit_SSD1306 oled_;
  bool present_ = false;
  uint32_t last_refresh_ms_ = 0;
};
