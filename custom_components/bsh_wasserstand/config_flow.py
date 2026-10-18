"""Config flow for BSH Wasserstand."""

from __future__ import annotations

import re
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
    CONF_HORIZON,
    CONF_SCAN_INTERVAL,
    CONF_STATION,
    CONF_USE_BAND,
    DEFAULT_HORIZON,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATION,
    DEFAULT_USE_BAND,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .parser import ParseError, parse_official

_SLUG = re.compile(r"^[a-z0-9_-]+$")


class BshConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a BSH gauge by its page name, e.g. travemuende."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            station = user_input[CONF_STATION].strip().lower()
            await self.async_set_unique_id(station)
            self._abort_if_unique_id_configured()
            if not _SLUG.match(station):
                errors[CONF_STATION] = "invalid_station"
            else:
                client = BshClient(async_get_clientsession(self.hass), station)
                try:
                    page, _ = await client.station_page()
                    official = parse_official(page)
                except StationNotFound:
                    errors[CONF_STATION] = "station_not_found"
                except BshError:
                    errors["base"] = "cannot_connect"
                except ParseError:
                    errors["base"] = "unexpected_page"
                else:
                    return self.async_create_entry(
                        title=official.station or station,
                        data={CONF_STATION: station},
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_STATION, default=DEFAULT_STATION): str}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BshOptionsFlow()


class BshOptionsFlow(OptionsFlow):
    """Polling interval, forecast horizon and alert behaviour."""

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
                        CONF_USE_BAND,
                        default=options.get(CONF_USE_BAND, DEFAULT_USE_BAND),
                    ): selector.BooleanSelector(),
                }
            ),
        )
