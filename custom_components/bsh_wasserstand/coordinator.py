"""Data coordinator for BSH Wasserstand."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BshClient, BshError
from .const import (
    CONF_DMI,
    DEFAULT_DMI,
    DMI_INTERVAL_MINUTES,
    DMI_PARAMETER,
    DMI_SEARCH_LAT,
    DMI_SEARCH_LON,
    DOMAIN,
    SEAS,
)
from .parser import (
    DmiForecast,
    OfficialForecast,
    ParseError,
    Station,
    WaterLevelData,
    nearest_wet_node,
    parse_dmi,
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
        self._dmi: DmiForecast | None = None
        self._dmi_node: tuple[float, float] | None = None
        self._dmi_fetched: datetime | None = None

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
        if self.config_entry.options.get(CONF_DMI, DEFAULT_DMI):
            await self._async_update_dmi(self._station)
        for message in errors:
            _LOGGER.warning("BSH %s: %s", self.client.station, message)
        return WaterLevelData(self._station, self._official, errors, self._dmi)

    async def _async_update_dmi(self, station: Station) -> None:
        """Refresh the DMI second opinion hourly; it is optional, never fatal."""
        now = datetime.now(UTC)
        due = timedelta(minutes=DMI_INTERVAL_MINUTES)
        if self._dmi_fetched and now - self._dmi_fetched < due:
            return
        if station.longitude is None or station.latitude is None:
            return
        self._dmi_fetched = now
        lon, lat = station.longitude, station.latitude
        try:
            if self._dmi_node is None:
                # The model coast is coarse: gauges in harbours are often on a
                # land node, so search the nearest node with water once.
                step = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00Z")
                cube = await self.client.dmi_cube(
                    lon - DMI_SEARCH_LON,
                    lat - DMI_SEARCH_LAT,
                    lon + DMI_SEARCH_LON,
                    lat + DMI_SEARCH_LAT,
                    step,
                )
                self._dmi_node = nearest_wet_node(cube, lon, lat, DMI_PARAMETER)
                if self._dmi_node is None:
                    _LOGGER.info("No DMI model node with water near %s", station.label)
                    return
            node_lon, node_lat = self._dmi_node
            document = await self.client.dmi_position(node_lon, node_lat)
            self._dmi = parse_dmi(document, lon, lat, DMI_PARAMETER)
        except (BshError, ParseError) as error:
            # Retry sooner than the regular hour, DMI throttles with HTTP 429.
            self._dmi_fetched = now - due + timedelta(minutes=15)
            _LOGGER.debug("DMI %s: %s", station.label, error)
