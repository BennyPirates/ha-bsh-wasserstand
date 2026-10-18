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
    """Create the warning and pre-warning thresholds."""
    async_add_entities(
        ThresholdNumber(entry, kind, pre)
        for kind in (HIGH, LOW)
        for pre in (False, True)
    )


class ThresholdNumber(BshEntity, RestoreNumber):
    """Water level that raises the warning or pre-warning level."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -300
    _attr_native_max_value = 400
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS

    def __init__(self, entry: BshConfigEntry, kind: str, pre: bool) -> None:
        # The warning keys are unchanged from v0.1 to keep entity IDs stable.
        key = f"{kind}_prewarning_threshold" if pre else f"{kind}_threshold"
        super().__init__(entry, key)
        self._key = f"{kind}_pre" if pre else kind

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._runtime.thresholds[self._key] = last.native_value
            self.coordinator.async_update_listeners()

    @property
    def native_value(self) -> float:
        return self._runtime.thresholds[self._key]

    async def async_set_native_value(self, value: float) -> None:
        self._runtime.thresholds[self._key] = value
        self.coordinator.async_update_listeners()
