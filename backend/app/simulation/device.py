"""Deterministic simulated ESP32-S3 device (PLAN.md section 22).

Used when no physical hardware is connected.  Behaviour is deterministic for a
given scenario + seed so that demos and tests are reproducible.  Every value
produced here is flagged ``simulated=True`` and must never be presented as real
hardware data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from app.schemas.telemetry import SensorReading, SensorStatus, TelemetrySnapshot


class Scenario(str, Enum):
    NORMAL = "normal"
    HEATWAVE = "heatwave"
    COLD = "cold"
    MOTION = "motion"
    HIGH_HUMIDITY = "high_humidity"
    SENSOR_FAULT = "sensor_fault"
    STALE = "stale"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ActuatorState:
    servo_angle: int = 90
    buzzer_active: bool = False
    buzzer_duration_ms: int = 0
    led_color: str = "off"
    last_updated: datetime = field(default_factory=_utcnow)


@dataclass
class SimulatedEsp32:
    """A deterministic model of the ESP32-S3 sensor/actuator node."""

    device_id: str = "esp32s3-clawsense-01"
    scenario: Scenario = Scenario.NORMAL
    seed: int = 1234
    tick: int = 0
    actuators: ActuatorState = field(default_factory=ActuatorState)
    firmware_version: str = "0.1.0-sim"
    #: When True, telemetry timestamps are frozen (to exercise stale-context).
    freeze_time: bool = False
    _frozen_at: datetime | None = None

    # -- scenario control --------------------------------------------------
    def set_scenario(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.tick = 0

    # -- sensor generation -------------------------------------------------
    def _wave(self, period: float, amplitude: float, offset: float) -> float:
        phase = (self.tick % period) / period
        return offset + amplitude * math.sin(2 * math.pi * phase)

    def _jitter(self, scale: float) -> float:
        # Deterministic, seed-based pseudo-noise (no RNG state to manage).
        x = math.sin((self.tick + 1) * 12.9898 + self.seed * 78.233) * 43758.5453
        frac = x - math.floor(x)
        return (frac - 0.5) * 2.0 * scale

    def generate_telemetry(self, now: datetime | None = None) -> TelemetrySnapshot:
        now = now or _utcnow()
        ts = now
        if self.freeze_time:
            if self._frozen_at is None:
                self._frozen_at = now
            ts = self._frozen_at

        temperature = 24.0 + self._wave(60, 2.0, 0.0) + self._jitter(0.3)
        humidity = 50.0 + self._wave(90, 8.0, 0.0) + self._jitter(1.0)
        motion = (self.tick % 12) in (5, 6)
        light = max(0.0, 300.0 + self._wave(40, 150.0, 0.0) + self._jitter(10.0))

        temp_status = SensorStatus.OK
        hum_status = SensorStatus.OK

        if self.scenario == Scenario.HEATWAVE:
            temperature = 41.0 + self._jitter(0.5)
        elif self.scenario == Scenario.COLD:
            temperature = 2.0 + self._jitter(0.5)
        elif self.scenario == Scenario.MOTION:
            motion = True
        elif self.scenario == Scenario.HIGH_HUMIDITY:
            humidity = 88.0 + self._jitter(1.0)
        elif self.scenario == Scenario.SENSOR_FAULT:
            temp_status = SensorStatus.ERROR
            humidity = 0.0
            hum_status = SensorStatus.ERROR
        elif self.scenario == Scenario.STALE:
            # Values keep their shape but the timestamp is frozen.
            self.freeze_time = True
            if self._frozen_at is None:
                self._frozen_at = now
            ts = self._frozen_at

        readings = {
            "temperature_c": SensorReading(
                sensor="temperature_c",
                value=None if temp_status == SensorStatus.ERROR else round(temperature, 2),
                unit="C",
                status=temp_status,
                timestamp=ts,
                simulated=True,
                detail="simulated sensor fault" if temp_status == SensorStatus.ERROR else "",
            ),
            "humidity_percent": SensorReading(
                sensor="humidity_percent",
                value=None if hum_status == SensorStatus.ERROR else round(humidity, 2),
                unit="%",
                status=hum_status,
                timestamp=ts,
                simulated=True,
            ),
            "motion": SensorReading(
                sensor="motion",
                value=bool(motion),
                unit="bool",
                status=SensorStatus.OK,
                timestamp=ts,
                simulated=True,
            ),
            "light_lux": SensorReading(
                sensor="light_lux",
                value=round(light, 1),
                unit="lux",
                status=SensorStatus.OK,
                timestamp=ts,
                simulated=True,
            ),
        }
        return TelemetrySnapshot(
            device_id=self.device_id,
            timestamp=ts,
            simulated=True,
            readings=readings,
        )

    def step(self, now: datetime | None = None) -> TelemetrySnapshot:
        self.tick += 1
        return self.generate_telemetry(now)

    # -- actuator application ---------------------------------------------
    def apply_command(self, action: str, parameters: dict) -> dict:
        """Apply an approved command and return the resulting actuator state."""
        self.actuators.last_updated = _utcnow()
        if action == "servo_move":
            self.actuators.servo_angle = int(parameters["angle_degrees"])
        elif action == "buzzer_beep":
            self.actuators.buzzer_active = True
            self.actuators.buzzer_duration_ms = int(parameters["duration_ms"])
        elif action == "set_status_led":
            self.actuators.led_color = str(parameters["color"])
        elif action == "no_op":
            pass
        return {
            "servo_angle": self.actuators.servo_angle,
            "buzzer_active": self.actuators.buzzer_active,
            "buzzer_duration_ms": self.actuators.buzzer_duration_ms,
            "led_color": self.actuators.led_color,
        }

    def state_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "firmware_version": self.firmware_version,
            "scenario": self.scenario.value,
            "servo_angle": self.actuators.servo_angle,
            "buzzer_active": self.actuators.buzzer_active,
            "buzzer_duration_ms": self.actuators.buzzer_duration_ms,
            "led_color": self.actuators.led_color,
            "simulated": True,
        }
