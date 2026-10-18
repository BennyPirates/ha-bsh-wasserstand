"""Sensors for BSH Wasserstand."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfLength
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
from .entity import BshConfigEntry, BshEntity
from .parser import Point


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
            OfficialForecastSensor(entry),
            OfficialExtremeSensor(entry, HIGH),
            OfficialExtremeSensor(entry, LOW),
            OfficialIssuedSensor(entry),
            ForecastRunSensor(entry),
            AlertLevelSensor(entry, HIGH),
            AlertLevelSensor(entry, LOW),
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

    @property
    def _level(self) -> tuple[str, float | None, list[Crossing]]:
        return alert_level(
            self.coordinator.data,
            dt_util.now(),
            self._runtime.thresholds,
            self._kind,
            self.horizon,
        )

    @property
    def native_value(self) -> str:
        return self._level[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        _, threshold, found = self._level
        thresholds = self._runtime.thresholds
        return {
            "threshold": threshold,
            "warning_threshold": thresholds[self._kind],
            "prewarning_threshold": thresholds[f"{self._kind}_pre"],
        } | describe(found, self._kind)
