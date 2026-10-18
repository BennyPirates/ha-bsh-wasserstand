"""BSH Wasserstand integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BshClient
from .const import CONF_SCAN_INTERVAL, CONF_STATION, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import BshCoordinator
from .entity import BshConfigEntry, BshRuntime

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SENSOR]

# Uncertainty band entities of v0.1 that no data source provides any more.
_REMOVED_KEYS = ("band_high", "band_low")


async def async_setup_entry(hass: HomeAssistant, entry: BshConfigEntry) -> bool:
    """Set up one BSH gauge."""
    client = BshClient(async_get_clientsession(hass), entry.data[CONF_STATION])
    interval = timedelta(
        minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    coordinator = BshCoordinator(hass, entry, client, interval)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = BshRuntime(coordinator)
    registry = er.async_get(hass)
    for key in _REMOVED_KEYS:
        unique_id = f"{client.station}_{key}"
        if entity_id := registry.async_get_entity_id("sensor", DOMAIN, unique_id):
            registry.async_remove(entity_id)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: BshConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BshConfigEntry) -> bool:
    """Unload one BSH gauge."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
