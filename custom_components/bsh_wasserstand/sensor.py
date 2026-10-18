"""Sensors for BSH Wasserstand."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfSpeed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .analysis import (
    HIGH,
    LEVELS,
    LOW,
    Crossing,
    alert_level,
    describe,
    extreme,
    upcoming,
)
from .const import WIND_ATTRIBUTION
from .entity import BshConfigEntry, BshEntity
from .parser import Point, WindPoint, distance_km


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BshConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the sensors of one gauge."""
    async_add_entities(
        [
            WaterLevelSensor(entry),
            ForecastExtremeSensor(entry, HIGH),
            ForecastExtremeSensor(entry, LOW),
            DmiExtremeSensor(entry, HIGH),
            DmiExtremeSensor(entry, LOW),
            OfficialForecastSensor(entry),
            OfficialExtremeSensor(entry, HIGH),
            OfficialExtremeSensor(entry, LOW),
            OfficialIssuedSensor(entry),
            ForecastRunSensor(entry),
            ReferenceDistanceSensor(entry, "gauge"),
            ReferenceDistanceSensor(entry, "dmi"),
            AlertLevelSensor(entry, HIGH),
            AlertLevelSensor(entry, LOW),
            WindSensor(entry),
        ]
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _series(points: list[Point]) -> list[dict[str, Any]]:
    return [{"time": p.time.isoformat(), "value": round(p.value, 1)} for p in points]


class LevelSensor(BshEntity, SensorEntity):
    """Water level in cm relative to NHN/SKN."""

    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_suggested_display_precision = 0


class WaterLevelSensor(LevelSensor):
    """Latest measured water level."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"history"})

    def __init__(self, entry: BshConfigEntry) -> None:
        super().__init__(entry, "water_level")

    @property
    def _latest(self) -> Point | None:
        station = self.coordinator.data.station
        return station.observations[-1] if station and station.observations else None

    @property
    def native_value(self) -> float | None:
        return self._latest.value if self._latest else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        station = self.coordinator.data.station
        attrs: dict[str, Any] = {
            "measured_at": _iso(self._latest.time) if self._latest else None
        }
        if station:
            attrs.update({k.lower(): v for k, v in station.references.items()})
            attrs["warning_level"] = station.warning
            attrs["history"] = _series(station.observations)
        return attrs


class ForecastExtremeSensor(LevelSensor):
    """Highest or lowest value of the BSH model forecast within the horizon."""

    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(self, entry: BshConfigEntry, kind: str) -> None:
        # Keys kept from v0.1 so entity IDs stay stable.
        super().__init__(entry, f"bsh_{kind}")
        self._kind = kind

    @property
    def _upcoming(self) -> list[Point]:
        station = self.coordinator.data.station
        if station is None:
            return []
        return upcoming(station.forecast, dt_util.now(), self.horizon)

    @property
    def available(self) -> bool:
        return super().available and bool(self._upcoming)

    @property
    def native_value(self) -> float | None:
        point = extreme(self._upcoming, self._kind)
        return round(point.value, 1) if point else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        station = self.coordinator.data.station
        point = extreme(self._upcoming, self._kind)
        attrs: dict[str, Any] = {
            "time": _iso(point.time) if point else None,
            "model_run": _iso(station.forecast_run) if station else None,
        }
        if self._kind == HIGH:
            attrs["forecast"] = _series(self._upcoming)
        return attrs


class DmiExtremeSensor(LevelSensor):
    """Highest or lowest value of the DMI storm surge model within the horizon."""

    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(self, entry: BshConfigEntry, kind: str) -> None:
        super().__init__(entry, f"dmi_{kind}")
        self._kind = kind

    @property
    def _upcoming(self) -> list[Point]:
        dmi = self.coordinator.data.dmi
        return upcoming(dmi.points, dt_util.now(), self.horizon) if dmi else []

    @property
    def available(self) -> bool:
        return super().available and bool(self._upcoming)

    @property
    def native_value(self) -> float | None:
        point = extreme(self._upcoming, self._kind)
        return round(point.value, 1) if point else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dmi = self.coordinator.data.dmi
        point = extreme(self._upcoming, self._kind)
        attrs: dict[str, Any] = {
            "time": _iso(point.time) if point else None,
            "model_longitude": round(dmi.longitude, 5) if dmi else None,
            "model_latitude": round(dmi.latitude, 5) if dmi else None,
            "distance_to_gauge_km": dmi.distance_km if dmi else None,
            "source": "DMI DKSS (Inner Danish Waters), CC BY 4.0",
        }
        if self._kind == HIGH and dmi:
            # Include the past hours of the run for comparison with measurements.
            attrs["forecast"] = _series(dmi.points)
        return attrs


class WindSensor(BshEntity, SensorEntity):
    """DWD wind at the reference point: current speed, hourly series."""

    _attr_device_class = SensorDeviceClass.WIND_SPEED
    _attr_native_unit_of_measurement = UnitOfSpeed.KNOTS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_attribution = WIND_ATTRIBUTION
    _unrecorded_attributes = frozenset({"forecast", "sources"})

    def __init__(self, entry: BshConfigEntry) -> None:
        super().__init__(entry, "wind")

    @property
    def _points(self) -> list[WindPoint]:
        wind = self.coordinator.data.wind
        return wind.points if wind else []

    @property
    def _current(self) -> WindPoint | None:
        now = dt_util.now()
        past = [p for p in self._points if p.time <= now]
        return past[-1] if past else None

    @property
    def available(self) -> bool:
        return super().available and self._current is not None

    @property
    def native_value(self) -> float | None:
        return self._current.speed if self._current else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current, now = self._current, dt_util.now()
        ahead = [p for p in self._points if now < p.time <= now + self.horizon]
        gusts = [p for p in ahead if p.gust is not None]
        top = max(gusts, key=lambda p: p.gust or 0) if gusts else None
        wind = self.coordinator.data.wind
        return {
            "direction": current.direction if current else None,
            "gust": current.gust if current else None,
            "max_gust": top.gust if top else None,
            "max_gust_time": _iso(top.time) if top else None,
            "sources": wind.sources if wind else [],
            "forecast": [
                {
                    "time": p.time.isoformat(),
                    "speed": p.speed,
                    "gust": p.gust,
                    "direction": p.direction,
                }
                for p in self._points
            ],
        }


class OfficialForecastSensor(BshEntity, SensorEntity):
    """Official forecast of the BSH water level service."""

    _unrecorded_attributes = frozenset({"periods", "text"})

    def __init__(self, entry: BshConfigEntry) -> None:
        super().__init__(entry, "official")

    @property
    def available(self) -> bool:
        official = self.coordinator.data.official
        return super().available and official is not None and bool(official.periods)

    @property
    def native_value(self) -> str | None:
        official = self.coordinator.data.official
        if not official or not official.periods:
            return None
        first = official.periods[0]
        return f"{first.lower:+d} bis {first.upper:+d} cm ({first.label})"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        official = self.coordinator.data.official
        if not official:
            return {}
        return {
            "area": official.area,
            "issued": _iso(official.issued),
            "warning": official.warning,
            "text": official.text,
            "periods": [
                {"label": p.label, "lower": p.lower, "upper": p.upper}
                for p in official.periods
            ],
            "summary": "\n".join(
                f"{p.label}: {p.lower:+d} bis {p.upper:+d} cm" for p in official.periods
            ),
        }


class OfficialExtremeSensor(LevelSensor):
    """Highest upper or lowest lower bound of the official forecast."""

    def __init__(self, entry: BshConfigEntry, kind: str) -> None:
        super().__init__(entry, f"official_{kind}")
        self._kind = kind

    @property
    def available(self) -> bool:
        official = self.coordinator.data.official
        return super().available and official is not None and bool(official.periods)

    @property
    def native_value(self) -> int | None:
        official = self.coordinator.data.official
        if not official or not official.periods:
            return None
        if self._kind == HIGH:
            return max(p.upper for p in official.periods)
        return min(p.lower for p in official.periods)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        official = self.coordinator.data.official
        if not official or not official.periods:
            return {}
        if self._kind == HIGH:
            period = max(official.periods, key=lambda p: p.upper)
        else:
            period = min(official.periods, key=lambda p: p.lower)
        return {"period": period.label}


class OfficialIssuedSensor(BshEntity, SensorEntity):
    """Time the official forecast was issued."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: BshConfigEntry) -> None:
        super().__init__(entry, "official_issued")

    @property
    def native_value(self) -> datetime | None:
        official = self.coordinator.data.official
        return official.issued if official else None


class ForecastRunSensor(BshEntity, SensorEntity):
    """Time of the automated model forecast."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: BshConfigEntry) -> None:
        super().__init__(entry, "forecast_run")

    @property
    def native_value(self) -> datetime | None:
        station = self.coordinator.data.station
        return station.forecast_run if station else None


class AlertLevelSensor(BshEntity, SensorEntity):
    """Two-stage alert level: none, pre-warning or warning."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = LEVELS

    def __init__(self, entry: BshConfigEntry, kind: str) -> None:
        super().__init__(entry, f"{kind}_alert")
        self._kind = kind
        self._previous: str | None = None

    @property
    def _level(self) -> tuple[str, float | None, list[Crossing]]:
        return alert_level(
            self.coordinator.data,
            dt_util.now(),
            self._runtime.thresholds,
            self._kind,
            self.horizon,
            self._previous,
        )

    @property
    def native_value(self) -> str:
        return self._level[0]

    def _handle_coordinator_update(self) -> None:
        # Remember the published level for the hysteresis of the next update.
        self._previous = self._level[0]
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        _, threshold, found = self._level
        thresholds = self._runtime.thresholds
        return {
            "threshold": threshold,
            "warning_threshold": thresholds[self._kind],
            "prewarning_threshold": thresholds[f"{self._kind}_pre"],
        } | describe(found, self._kind)


class ReferenceDistanceSensor(BshEntity, SensorEntity):
    """Distance from the configured reference point to a data source."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:map-marker-distance"

    def __init__(self, entry: BshConfigEntry, target: str) -> None:
        super().__init__(entry, f"reference_distance_{target}")
        self._target = target

    @property
    def _target_position(self) -> tuple[float, float] | None:
        data = self.coordinator.data
        if self._target == "dmi":
            return (data.dmi.longitude, data.dmi.latitude) if data.dmi else None
        station = data.station
        if station and station.longitude is not None and station.latitude is not None:
            return station.longitude, station.latitude
        return None

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.reference is not None
            and self._target_position is not None
        )

    @property
    def native_value(self) -> float | None:
        reference, target = self.reference, self._target_position
        if reference is None or target is None:
            return None
        return round(distance_km(*reference, *target), 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        reference, target = self.reference, self._target_position
        return {
            "reference_longitude": reference[0] if reference else None,
            "reference_latitude": reference[1] if reference else None,
            "target_longitude": round(target[0], 5) if target else None,
            "target_latitude": round(target[1], 5) if target else None,
        }
