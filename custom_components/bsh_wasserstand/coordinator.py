"""Data coordinator for BSH Wasserstand."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BshClient, BshError
from .const import DOMAIN
from .parser import (
    FigureData,
    OfficialForecast,
    ParseError,
    WaterLevelData,
    parse_figure,
    parse_official,
)

_LOGGER = logging.getLogger(__name__)


class BshCoordinator(DataUpdateCoordinator[WaterLevelData]):
    """Fetch the station page and figure; keep the last good part on errors."""

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
        self._figure: FigureData | None = None
        self._official: OfficialForecast | None = None

    async def _async_update_data(self) -> WaterLevelData:
        errors: list[str] = []

        try:
            page, changed = await self.client.station_page()
            if changed or self._official is None:
                self._official = parse_official(page)
        except (BshError, ParseError) as error:
            errors.append(f"official forecast: {error}")

        try:
            page, changed = await self.client.figure_page()
            if changed or self._figure is None:
                self._figure = await self.hass.async_add_executor_job(
                    parse_figure, page
                )
        except (BshError, ParseError) as error:
            errors.append(f"model figure: {error}")

        if self._figure is None and self._official is None:
            raise UpdateFailed("; ".join(errors))
        for message in errors:
            _LOGGER.warning("BSH %s: %s", self.client.station, message)
        return WaterLevelData(self._figure, self._official, errors)
