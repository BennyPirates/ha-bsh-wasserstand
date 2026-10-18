"""Config flow for BSH Wasserstand."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BshClient, BshError, StationNotFound
from .const import (
    CONF_DMI,
    CONF_HORIZON,
    CONF_REFERENCE,
    CONF_SCAN_INTERVAL,
    CONF_STATION,
    CONF_WIND,
    DEFAULT_DMI,
    DEFAULT_HORIZON,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATION,
    DEFAULT_WIND,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .parser import ParseError, parse_station, parse_stations


class BshConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one gauge of the BSH water level forecast."""

    VERSION = 1

    def __init__(self) -> None:
        self._stations: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        client = BshClient(async_get_clientsession(self.hass), DEFAULT_STATION)

        if user_input is not None:
            station = user_input[CONF_STATION].strip().lower()
            await self.async_set_unique_id(station)
            self._abort_if_unique_id_configured()
            client.station = station
            try:
                document, _ = await client.station_data()
                data = parse_station(document)
            except StationNotFound:
                errors[CONF_STATION] = "station_not_found"
            except BshError:
                errors["base"] = "cannot_connect"
            except ParseError:
                errors["base"] = "unexpected_data"
            else:
                return self.async_create_entry(
                    title=data.label or station, data={CONF_STATION: station}
                )

        if not self._stations:
            try:
                self._stations = parse_stations(await client.stations())
            except BshError:
                self._stations = {}

        field: Any = str
        if self._stations:
            field = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=key, label=label)
                        for key, label in sorted(
                            self._stations.items(), key=lambda item: item[1]
                        )
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    sort=False,
                )
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_STATION, default=DEFAULT_STATION): field}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BshOptionsFlow()


class BshOptionsFlow(OptionsFlow):
    """Polling interval and forecast horizon."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=180,
                            unit_of_measurement="min",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_HORIZON,
                        default=options.get(CONF_HORIZON, DEFAULT_HORIZON),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=6,
                            max=168,
                            unit_of_measurement="h",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_DMI, default=options.get(CONF_DMI, DEFAULT_DMI)
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_WIND, default=options.get(CONF_WIND, DEFAULT_WIND)
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        CONF_REFERENCE,
                        description={"suggested_value": options.get(CONF_REFERENCE)},
                    ): selector.LocationSelector(
                        selector.LocationSelectorConfig(radius=False)
                    ),
                }
            ),
        )
