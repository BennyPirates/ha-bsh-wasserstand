"""Shared BSH Wasserstand entity helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .analysis import HIGH, LOW
from .const import (
    ATTRIBUTION,
    CONF_HORIZON,
    DEFAULT_HIGH_THRESHOLD,
    DEFAULT_HORIZON,
    DEFAULT_LOW_THRESHOLD,
    DOMAIN,
    PAGE_URL,
)
from .coordinator import BshCoordinator


@dataclass(slots=True)
class BshRuntime:
    """Objects shared by the platforms of one config entry."""

    coordinator: BshCoordinator
    thresholds: dict[str, float] = field(
        default_factory=lambda: {
            HIGH: DEFAULT_HIGH_THRESHOLD,
            LOW: DEFAULT_LOW_THRESHOLD,
        }
    )


type BshConfigEntry = ConfigEntry[BshRuntime]


class BshEntity(CoordinatorEntity[BshCoordinator]):
    """Base entity of one BSH gauge."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, entry: BshConfigEntry, key: str) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._runtime = entry.runtime_data
        station = self.coordinator.client.station
        self._attr_translation_key = key
        self._attr_unique_id = f"{station}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, station)},
            name=f"Pegel {entry.title}",
            manufacturer="Bundesamt für Seeschifffahrt und Hydrographie",
            model="Wasserstandsvorhersage Ostsee",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=PAGE_URL.format(station=station),
        )

    @property
    def horizon(self) -> timedelta:
        return timedelta(hours=self._entry.options.get(CONF_HORIZON, DEFAULT_HORIZON))
