"""Event generation engine (PLAN.md section 5.2 / 13).

Converts raw telemetry into typed, meaningful events using change detection,
debouncing, and edge detection (e.g. motion rising/falling edges).  Emits only
meaningful events so the dashboard and audit log are not flooded with noise.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.schemas.events import EventCategory, EventRecord, EventType, Severity
from app.schemas.telemetry import SensorStatus, TelemetrySnapshot
from app.services.event_bus import EventBus

TEMP_EPSILON = 0.5
HUMIDITY_EPSILON = 1.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventEngine:
    def __init__(self, settings: Settings, bus: EventBus) -> None:
        self.settings = settings
        self.bus = bus
        self._last_temp: float | None = None
        self._last_humidity: float | None = None
        self._last_motion: bool | None = None
        self._temp_high_active = False
        self._temp_low_active = False
        self._humidity_high_active = False

    def reset(self) -> None:
        self._last_temp = None
        self._last_humidity = None
        self._last_motion = None
        self._temp_high_active = False
        self._temp_low_active = False
        self._humidity_high_active = False

    def process(self, snapshot: TelemetrySnapshot) -> list[EventRecord]:
        """Return newly generated events for a telemetry snapshot."""
        events: list[EventRecord] = []

        temp_reading = snapshot.readings.get("temperature_c")
        humidity_reading = snapshot.readings.get("humidity_percent")
        motion_reading = snapshot.readings.get("motion")

        # -- temperature ----------------------------------------------------
        if temp_reading is not None and temp_reading.status == SensorStatus.OK:
            temp = temp_reading.value
            if isinstance(temp, (int, float)):
                if self._last_temp is None or abs(temp - self._last_temp) >= TEMP_EPSILON:
                    events.append(
                        self._event(
                            EventType.TEMPERATURE_UPDATED,
                            EventCategory.SENSOR_READING,
                            snapshot,
                            {"temperature_c": temp},
                        )
                    )
                    self._last_temp = float(temp)

                high = temp > self.settings.temp_high_c
                low = temp < self.settings.temp_low_c
                if high and not self._temp_high_active:
                    events.append(
                        self._event(
                            EventType.THRESHOLD_EXCEEDED,
                            EventCategory.SENSOR_THRESHOLD,
                            snapshot,
                            {
                                "sensor": "temperature_c",
                                "value": temp,
                                "threshold": self.settings.temp_high_c,
                                "direction": "above",
                            },
                            severity=Severity.WARNING,
                        )
                    )
                if low and not self._temp_low_active:
                    events.append(
                        self._event(
                            EventType.THRESHOLD_EXCEEDED,
                            EventCategory.SENSOR_THRESHOLD,
                            snapshot,
                            {
                                "sensor": "temperature_c",
                                "value": temp,
                                "threshold": self.settings.temp_low_c,
                                "direction": "below",
                            },
                            severity=Severity.WARNING,
                        )
                    )
                self._temp_high_active = high
                self._temp_low_active = low

        # -- humidity -------------------------------------------------------
        if humidity_reading is not None and humidity_reading.status == SensorStatus.OK:
            humidity = humidity_reading.value
            if isinstance(humidity, (int, float)):
                if (
                    self._last_humidity is None
                    or abs(humidity - self._last_humidity) >= HUMIDITY_EPSILON
                ):
                    events.append(
                        self._event(
                            EventType.HUMIDITY_UPDATED,
                            EventCategory.SENSOR_READING,
                            snapshot,
                            {"humidity_percent": humidity},
                        )
                    )
                    self._last_humidity = float(humidity)
                high = humidity > self.settings.humidity_high_percent
                if high and not self._humidity_high_active:
                    events.append(
                        self._event(
                            EventType.THRESHOLD_EXCEEDED,
                            EventCategory.SENSOR_THRESHOLD,
                            snapshot,
                            {
                                "sensor": "humidity_percent",
                                "value": humidity,
                                "threshold": self.settings.humidity_high_percent,
                                "direction": "above",
                            },
                            severity=Severity.WARNING,
                        )
                    )
                self._humidity_high_active = high

        # -- motion (edge detection) ---------------------------------------
        if motion_reading is not None and motion_reading.status == SensorStatus.OK:
            motion = bool(motion_reading.value)
            if self._last_motion is None:
                self._last_motion = motion
            elif motion != self._last_motion:
                events.append(
                    self._event(
                        EventType.MOTION_DETECTED if motion else EventType.MOTION_CLEARED,
                        EventCategory.SENSOR_READING,
                        snapshot,
                        {"motion": motion},
                    )
                )
                self._last_motion = motion

        return events

    @staticmethod
    def _event(
        event_type: EventType,
        category: EventCategory,
        snapshot: TelemetrySnapshot,
        details: dict,
        severity: Severity = Severity.INFO,
    ) -> EventRecord:
        return EventRecord(
            event_type=event_type,
            category=category,
            source="event_engine",
            severity=severity,
            device_id=snapshot.device_id,
            details=details,
            simulated=snapshot.simulated,
        )
