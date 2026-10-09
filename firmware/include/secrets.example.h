#pragma once

// ---------------------------------------------------------------------------
// ClawSense WiFi secrets — TEMPLATE ONLY.
//
// Copy this file to `secrets.h` (same directory) and fill in real values:
//
//     cp include/secrets.example.h include/secrets.h
//
// `secrets.h` is listed in .gitignore and MUST NEVER be committed.
// config.h includes it only when present (`__has_include`), so a fresh clone
// still builds and simply runs without WiFi (AP-less, local-only operation).
//
// Never hard-code real credentials in any other file.
// ---------------------------------------------------------------------------

#define WIFI_SSID     "REPLACE_WITH_YOUR_SSID"
#define WIFI_PASSWORD "REPLACE_WITH_YOUR_PASSWORD"

// Optional: override the hostname advertised on the LAN.
// #define WIFI_HOSTNAME "clawsense-esp32"
