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

from .analysis import HIGH, LOW, extreme, hourly, model_series, upcoming
from .const import MODELS
from .entity import BshConfigEntry, BshEntity
from .parser import Point


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BshConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the sensors of one gauge."""
    entities: list[SensorEntity] = [WaterLevelSensor(entry)]
    for model in MODELS:
        entities += [
            ModelExtremeSensor(entry, model, HIGH),
            ModelExtremeSensor(entry, model, LOW),
        ]
    entities += [
        BandExtremeSensor(entry, HIGH),
        BandExtremeSensor(entry, LOW),
        OfficialForecastSensor(entry),
        OfficialExtremeSensor(entry, HIGH),
        OfficialExtremeSensor(entry, LOW),
        OfficialIssuedSensor(entry),
    ]
    async_add_entities(entities)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class LevelSensor(BshEntity, SensorEntity):
    """Water level in cm relative to NHN/SKN."""

    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_suggested_display_precision = 0


class WaterLevelSensor(LevelSensor):
    """Latest measured water level."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: BshConfigEntry) -> None:
        super().__init__(entry, "water_level")

    @property
    def _latest(self) -> Point | None:
        figure = self.coordinator.data.figure
        return figure.observations[-1] if figure and figure.observations else None

    @property
    def native_value(self) -> float | None:
        return self._latest.value if self._latest else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        figure = self.coordinator.data.figure
        attrs: dict[str, Any] = {
            "measured_at": _iso(self._latest.time) if self._latest else None
        }
        if figure:
            attrs.update({k.lower(): v for k, v in figure.references.items()})
        return attrs


class ModelExtremeSensor(LevelSensor):
    """Highest or lowest value of one model run within the horizon."""

    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(self, entry: BshConfigEntry, model: str, kind: str) -> None:
        super().__init__(entry, f"{model}_{kind}")
        self._model = model
        self._kind = kind

    @property
    def _upcoming(self) -> list[Point]:
        series = model_series(self.coordinator.data, self._model)
        return upcoming(series, dt_util.now(), self.horizon)

    @property
    def available(self) -> bool:
        return super().available and bool(self._upcoming)

    @property
    def native_value(self) -> float | None:
        point = extreme(self._upcoming, self._kind)
        return round(point.value, 1) if point else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        point = extreme(self._upcoming, self._kind)
        attrs: dict[str, Any] = {
            "time": _iso(point.time) if point else None,
            "model_run": data.figure.models[self._model].run
            if data.figure and self._model in data.figure.models
            else None,
        }
        if self._kind == HIGH:
            band = {
                b.time: b
                for b in (
                    data.figure.models[self._model].band
                    if data.figure and self._model in data.figure.models
                    else []
                )
            }
            attrs["forecast"] = [
                {
                    "time": p.time.isoformat(),
                    "value": round(p.value, 1),
                    "lower": round(band[p.time].lower, 1) if p.time in band else None,
                    "upper": round(band[p.time].upper, 1) if p.time in band else None,
                }
                for p in hourly(self._upcoming)
            ]
        return attrs


class BandExtremeSensor(LevelSensor):
    """Most extreme value including the uncertainty band of all models."""

    def __init__(self, entry: BshConfigEntry, kind: str) -> None:
        super().__init__(entry, f"band_{kind}")
        self._kind = kind

    @property
    def _best(self) -> tuple[str, Point] | None:
        now = dt_util.now()
        found = []
        for model in MODELS:
            series = model_series(self.coordinator.data, model, self._kind)
            if point := extreme(upcoming(series, now, self.horizon), self._kind):
                found.append((model, point))
        if not found:
            return None
        pick = max if self._kind == HIGH else min
        return pick(found, key=lambda item: item[1].value)

    @property
    def available(self) -> bool:
        return super().available and self._best is not None

    @property
    def native_value(self) -> float | None:
        best = self._best
        return round(best[1].value, 1) if best else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        best = self._best
        return {
            "time": _iso(best[1].time) if best else None,
            "model": MODELS[best[0]] if best else None,
        }


class OfficialForecastSensor(BshEntity, SensorEntity):
    """Official forecast text of the BSH water level service."""

    _unrecorded_attributes = frozenset({"periods"})

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
            "notice": official.notice,
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
