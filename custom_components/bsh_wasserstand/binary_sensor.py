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

from .analysis import HIGH, LOW, Crossing, crossings, describe
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
            self.horizon,
        )

    @property
    def is_on(self) -> bool:
        return bool(self._crossings)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"threshold": self._threshold} | describe(self._crossings, self._kind)


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
        station = data.station
        if station and station.observations:
            age = dt_util.now() - station.observations[-1].time
            if age > STALE_AFTER:
                reasons.append(f"latest measurement is {age} old")
        return reasons

    @property
    def is_on(self) -> bool:
        return bool(self._reasons())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"reasons": self._reasons()}
