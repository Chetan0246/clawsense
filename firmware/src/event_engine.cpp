// ===========================================================================
// Event engine implementation.
//
// All edge detection is done against the previous *good* reading.  Events are
// debounced per channel so a noisy ADC cannot flood the bounded context
// buffer.  Nothing here blocks or allocates.
// ===========================================================================

#include "event_engine.h"

#include <math.h>

#include "context_buffer.h"

const char* eventTypeToString(EventType type) {
  switch (type) {
    case EventType::BOOT:                 return "BOOT";
    case EventType::TEMPERATURE_UPDATED:  return "TEMPERATURE_UPDATED";
    case EventType::HUMIDITY_UPDATED:     return "HUMIDITY_UPDATED";
    case EventType::LIGHT_LEVEL_CHANGED:  return "LIGHT_LEVEL_CHANGED";
    case EventType::TEMPERATURE_HIGH:     return "TEMPERATURE_HIGH";
    case EventType::TEMPERATURE_LOW:      return "TEMPERATURE_LOW";
    case EventType::HUMIDITY_HIGH:        return "HUMIDITY_HIGH";
    case EventType::MOTION_DETECTED:      return "MOTION_DETECTED";
    case EventType::MOTION_CLEARED:       return "MOTION_CLEARED";
    case EventType::SENSOR_ERROR:         return "SENSOR_ERROR";
    case EventType::ACTION_APPROVED:      return "ACTION_APPROVED";
    case EventType::ACTION_REJECTED:      return "ACTION_REJECTED";
    case EventType::COMMAND_ACKNOWLEDGED: return "COMMAND_ACKNOWLEDGED";
    case EventType::COMMAND_REJECTED:     return "COMMAND_REJECTED";
    case EventType::FALLBACK_ACTIVATED:   return "FALLBACK_ACTIVATED";
    case EventType::AGENT_TIMEOUT:        return "AGENT_TIMEOUT";
    case EventType::STATE_TRANSITION:     return "STATE_TRANSITION";
    case EventType::RECOVERY:             return "RECOVERY";
    case EventType::BUTTON_ACK:           return "BUTTON_ACK";
    case EventType::SENSOR_REREAD_REQUESTED:
      return "SENSOR_REREAD_REQUESTED";
  }
  return "UNKNOWN";
}

void EventEngine::begin(uint32_t now_ms) {
  have_temp_ = have_humidity_ = have_light_ = false;
  have_motion_ = false;
  last_temp_ = last_humidity_ = last_light_ = NAN;
  temp_high_ = temp_low_ = humidity_high_ = false;
  last_motion_ = false;
  motion_edge_ms_ = 0;
  last_temp_event_ms_ = last_humidity_event_ms_ = last_light_event_ms_ = 0;
  (void)now_ms;
}

void EventEngine::emit(EventType type, float value, const char* detail,
                       uint32_t now_ms, ContextBuffer& context) {
  Event e;
  e.type = type;
  e.timestamp_ms = now_ms;
  e.value = value;
  if (detail != nullptr) {
    strlcpy(e.detail, detail, sizeof(e.detail));
  }
  context.pushEvent(e);
}

void EventEngine::update(const SensorSnapshot& s, uint32_t now_ms,
                         ContextBuffer& context) {
  // -- temperature --------------------------------------------------------
#if CONFIG_ENABLE_TEMPERATURE
  if (s.temperature.configured) {
    if (s.temperature.status == SensorStatus::ERROR) {
      if ((uint32_t)(now_ms - last_temp_event_ms_) >= EVENT_MIN_INTERVAL_MS) {
        emit(EventType::SENSOR_ERROR, NAN, "temperature read error", now_ms, context);
        last_temp_event_ms_ = now_ms;
      }
    } else if (s.temperature.valid) {
      const float t = s.temperature.value;

      // Threshold edges (debounced by the event interval).
      const bool is_high = t > TEMP_HIGH_C;
      const bool is_low = t < TEMP_LOW_C;
      if ((uint32_t)(now_ms - last_temp_event_ms_) >= EVENT_MIN_INTERVAL_MS) {
        if (is_high && !temp_high_) {
          emit(EventType::TEMPERATURE_HIGH, t, "temperature above high threshold",
               now_ms, context);
          last_temp_event_ms_ = now_ms;
        } else if (is_low && !temp_low_) {
          emit(EventType::TEMPERATURE_LOW, t, "temperature below low threshold",
               now_ms, context);
          last_temp_event_ms_ = now_ms;
        } else if (have_temp_ && fabsf(t - last_temp_) >= TEMP_CHANGE_THRESHOLD_C) {
          emit(EventType::TEMPERATURE_UPDATED, t, "temperature changed",
               now_ms, context);
          last_temp_event_ms_ = now_ms;
        }
      }
      temp_high_ = is_high;
      temp_low_ = is_low;
      last_temp_ = t;
      have_temp_ = true;
    }
  }
#endif

  // -- humidity -----------------------------------------------------------
#if CONFIG_ENABLE_HUMIDITY
  if (s.humidity.configured) {
    if (s.humidity.status == SensorStatus::ERROR) {
      if ((uint32_t)(now_ms - last_humidity_event_ms_) >= EVENT_MIN_INTERVAL_MS) {
        emit(EventType::SENSOR_ERROR, NAN, "humidity read error", now_ms, context);
        last_humidity_event_ms_ = now_ms;
      }
    } else if (s.humidity.valid) {
      const float h = s.humidity.value;
      const bool is_high = h > HUMIDITY_HIGH_PERCENT;
      if ((uint32_t)(now_ms - last_humidity_event_ms_) >= EVENT_MIN_INTERVAL_MS) {
        if (is_high && !humidity_high_) {
          emit(EventType::HUMIDITY_HIGH, h, "humidity above high threshold",
               now_ms, context);
          last_humidity_event_ms_ = now_ms;
        } else if (have_humidity_ &&
                   fabsf(h - last_humidity_) >= HUMIDITY_CHANGE_THRESHOLD_PCT) {
          emit(EventType::HUMIDITY_UPDATED, h, "humidity changed",
               now_ms, context);
          last_humidity_event_ms_ = now_ms;
        }
      }
      humidity_high_ = is_high;
      last_humidity_ = h;
      have_humidity_ = true;
    }
  }
#endif

  // -- light --------------------------------------------------------------
#if CONFIG_ENABLE_LIGHT
  if (s.light.configured && s.light.valid) {
    const float l = s.light.value;
    if ((uint32_t)(now_ms - last_light_event_ms_) >= EVENT_MIN_INTERVAL_MS) {
      if (have_light_ && fabsf(l - last_light_) >= LIGHT_CHANGE_THRESHOLD_LUX) {
        emit(EventType::LIGHT_LEVEL_CHANGED, l, "light level changed",
             now_ms, context);
        last_light_event_ms_ = now_ms;
      }
    }
    last_light_ = l;
    have_light_ = true;
  }
#endif

  // -- motion (rising / falling edges, debounced) -------------------------
#if CONFIG_ENABLE_MOTION
  if (s.motion_status == SensorStatus::OK) {
    const bool now_motion = s.motion;
    if (have_motion_ && now_motion != last_motion_ &&
        (uint32_t)(now_ms - motion_edge_ms_) >= MOTION_DEBOUNCE_MS) {
      if (now_motion) {
        emit(EventType::MOTION_DETECTED, 1.0f, "motion detected", now_ms, context);
      } else {
        emit(EventType::MOTION_CLEARED, 0.0f, "motion cleared", now_ms, context);
      }
      motion_edge_ms_ = now_ms;
    }
    last_motion_ = now_motion;
    have_motion_ = true;
  }
#endif
}
