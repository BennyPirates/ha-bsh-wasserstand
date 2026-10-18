"""Alert thresholds for BSH Wasserstand."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .analysis import HIGH, LOW
from .entity import BshConfigEntry, BshEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BshConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the threshold numbers."""
    async_add_entities([ThresholdNumber(entry, HIGH), ThresholdNumber(entry, LOW)])


class ThresholdNumber(BshEntity, RestoreNumber):
    """Water level that triggers the expected high or low water sensor."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -300
    _attr_native_max_value = 400
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS

    def __init__(self, entry: BshConfigEntry, kind: str) -> None:
        super().__init__(entry, f"{kind}_threshold")
        self._kind = kind

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._runtime.thresholds[self._kind] = last.native_value
            self.coordinator.async_update_listeners()

    @property
    def native_value(self) -> float:
        return self._runtime.thresholds[self._kind]

    async def async_set_native_value(self, value: float) -> None:
        self._runtime.thresholds[self._kind] = value
        self.coordinator.async_update_listeners()
