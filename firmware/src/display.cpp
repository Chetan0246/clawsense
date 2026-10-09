// ===========================================================================
// OLED display implementation.
//
// The display is purely informative; no safety decision depends on it.  If it
// is missing the rest of the system behaves identically.
// ===========================================================================

#include "display.h"

Display::Display()
    : oled_(CONFIG_OLED_WIDTH, CONFIG_OLED_HEIGHT, &Wire, -1) {}

void Display::formatScalar(const SensorValue& v, char* out, size_t len) {
  if (!v.configured) {
    snprintf(out, len, "N/C");
    return;
  }
  if (!v.valid) {
    snprintf(out, len, "--");
    return;
  }
  if (v.status == SensorStatus::STALE) {
    snprintf(out, len, "stale");
    return;
  }
  snprintf(out, len, "%.1f", (double)v.value);
}

bool Display::begin() {
#if !CONFIG_ENABLE_DISPLAY
  present_ = false;
  return false;
#else
  Wire.begin(CONFIG_PIN_I2C_SDA, CONFIG_PIN_I2C_SCL);
  // 0x3C is the SSD1306 default.  Probe before init so a missing panel is not
  // reported as a hard failure.
  Wire.beginTransmission(CONFIG_OLED_ADDR);
  if (Wire.endTransmission() != 0) {
    present_ = false;
    CS_LOGW("OLED not detected at 0x%02X; continuing without display",
            CONFIG_OLED_ADDR);
    return false;
  }
  if (!oled_.begin(SSD1306_SWITCHCAPVCC, CONFIG_OLED_ADDR)) {
    present_ = false;
    CS_LOGW("OLED init failed; continuing without display");
    return false;
  }
  present_ = true;
  oled_.clearDisplay();
  oled_.setTextColor(SSD1306_WHITE);
  oled_.setTextSize(1);
  oled_.setCursor(0, 0);
  oled_.println("ClawSense booting...");
  oled_.display();
  CS_LOGI("OLED initialised");
  return true;
#endif
}

void Display::update(uint32_t now_ms, SystemState state,
                     ControllerAuthority authority, const SensorSnapshot& sensors,
                     WifiState wifi, const char* last_cmd_action,
                     const char* last_cmd_detail) {
  if (!present_) {
    return;
  }
  if ((uint32_t)(now_ms - last_refresh_ms_) < DISPLAY_REFRESH_INTERVAL_MS) {
    return;
  }
  last_refresh_ms_ = now_ms;

  char temp[16], humid[16], light[16];

  formatScalar(sensors.temperature, temp, sizeof(temp));
  formatScalar(sensors.humidity, humid, sizeof(humid));
  formatScalar(sensors.light, light, sizeof(light));

  oled_.clearDisplay();
  oled_.setTextSize(1);
  oled_.setCursor(0, 0);

  // -- header --------------------------------------------------------------
  oled_.print("ClawSense ");
  oled_.println(FIRMWARE_VERSION);

  // -- state + authority ---------------------------------------------------
  oled_.print("State: ");
  oled_.println(systemStateToString(state));
  oled_.print("Ctrl : ");
  oled_.println(controllerAuthorityToString(authority));

  // -- sensors -------------------------------------------------------------
  oled_.print("T:");
  oled_.print(temp);
  oled_.print("C H:");
  oled_.print(humid);
  oled_.println("%");

  oled_.print("M:");
  if (sensors.motion_status == SensorStatus::NOT_CONFIGURED) {
    oled_.print("N/C");
  } else if (!sensors.motion_valid) {
    oled_.print("--");
  } else {
    oled_.print(sensors.motion ? "YES" : "no");
  }
  oled_.print(" L:");
  oled_.print(light);
  oled_.println("lx");

  // -- connectivity --------------------------------------------------------
  oled_.print("WiFi: ");
  oled_.println(wifiStateToString(wifi));

  // -- last command --------------------------------------------------------
  oled_.print("Cmd : ");
  oled_.println((last_cmd_action && last_cmd_action[0]) ? last_cmd_action : "-");
  oled_.print("Res : ");
  oled_.println((last_cmd_detail && last_cmd_detail[0]) ? last_cmd_detail : "-");

  oled_.display();
}
