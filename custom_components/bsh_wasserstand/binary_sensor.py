"""Alert binary sensors for BSH Wasserstand."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .analysis import HIGH, LOW, Crossing, crossings
from .entity import BshConfigEntry, BshEntity

STALE_AFTER = timedelta(hours=3)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BshConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the alert sensors."""
    async_add_entities(
        [AlertSensor(entry, HIGH), AlertSensor(entry, LOW), DataProblemSensor(entry)]
    )


class AlertSensor(BshEntity, BinarySensorEntity):
    """On when observation or any forecast reaches the threshold."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, entry: BshConfigEntry, kind: str) -> None:
        super().__init__(entry, f"{kind}_expected")
        self._kind = kind

    @property
    def _threshold(self) -> float:
        return self._runtime.thresholds[self._kind]

    @property
    def _crossings(self) -> list[Crossing]:
        return crossings(
            self.coordinator.data,
            dt_util.now(),
            self._threshold,
            self._kind,
            self.use_band,
            self.horizon,
        )

    @property
    def is_on(self) -> bool:
        return bool(self._crossings)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        found = self._crossings
        timed = [c for c in found if c.first]
        first = min(timed, key=lambda c: c.first.time) if timed else None  # type: ignore[union-attr]
        peaks = [c.extreme for c in found if c.extreme]
        pick = max if self._kind == HIGH else min
        peak = pick(peaks, key=lambda p: p.value) if peaks else None
        return {
            "threshold": self._threshold,
            "uses_uncertainty_band": self.use_band,
            "sources": [c.source for c in found],
            "first_time": first.first.time.isoformat()
            if first and first.first
            else None,
            "first_source": first.source if first else None,
            "peak": round(peak.value, 1) if peak else None,
            "peak_time": peak.time.isoformat() if peak else None,
        }


class DataProblemSensor(BshEntity, BinarySensorEntity):
    """On when the BSH data could not be refreshed or is outdated."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: BshConfigEntry) -> None:
        super().__init__(entry, "data_problem")

    @property
    def available(self) -> bool:
        return True

    def _reasons(self) -> list[str]:
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            return ["update failed"]
        data = self.coordinator.data
        reasons = list(data.errors)
        figure = data.figure
        if figure and figure.observations:
            age = dt_util.now() - figure.observations[-1].time
            if age > STALE_AFTER:
                reasons.append(f"latest measurement is {age} old")
        return reasons

    @property
    def is_on(self) -> bool:
        return bool(self._reasons())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"reasons": self._reasons()}
