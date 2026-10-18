"""Data coordinator for BSH Wasserstand."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BshClient, BshError
from .const import DOMAIN, SEAS
from .parser import (
    OfficialForecast,
    ParseError,
    Station,
    WaterLevelData,
    parse_official,
    parse_station,
)

_LOGGER = logging.getLogger(__name__)


class BshCoordinator(DataUpdateCoordinator[WaterLevelData]):
    """Fetch station data and the official area table; keep last good parts."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: BshClient,
        interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{client.station}",
            update_interval=interval,
            config_entry=entry,
        )
        self.client = client
        self._station: Station | None = None
        self._official: OfficialForecast | None = None

    async def _async_update_data(self) -> WaterLevelData:
        errors: list[str] = []

        try:
            document, changed = await self.client.station_data()
            if changed or self._station is None:
                self._station = parse_station(document)
        except (BshError, ParseError) as error:
            errors.append(f"station data: {error}")

        station = self._station
        sea = SEAS.get(station.region or "") if station else None
        if station and sea:
            try:
                document, changed = await self.client.area_table(sea)
                if changed or self._official is None:
                    self._official = parse_official(document, station.area)
            except (BshError, ParseError) as error:
                # North Sea tables use another layout; only report Baltic issues.
                if sea == "ostsee":
                    errors.append(f"official forecast: {error}")

        if self._station is None:
            raise UpdateFailed("; ".join(errors))
        for message in errors:
            _LOGGER.warning("BSH %s: %s", self.client.station, message)
        return WaterLevelData(self._station, self._official, errors)
