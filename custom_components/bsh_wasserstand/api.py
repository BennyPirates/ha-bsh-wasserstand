"""HTTP client for the BSH water level API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import AREA_URL, DMI_PARAMETER, DMI_URL, STATION_URL, STATIONS_URL

TIMEOUT = aiohttp.ClientTimeout(total=60)


class BshError(Exception):
    """The BSH service could not be reached."""


class StationNotFound(BshError):
    """The station does not exist."""


@dataclass(slots=True)
class _Cached:
    validators: dict[str, str]
    document: Any


class BshClient:
    """Download JSON documents, reusing unchanged ones via HTTP validators."""

    def __init__(self, session: aiohttp.ClientSession, station: str) -> None:
        self._session = session
        self.station = station
        self._cache: dict[str, _Cached] = {}

    async def _get(self, url: str) -> tuple[Any, bool]:
        """Return the document and whether it changed since the last call."""
        cached = self._cache.get(url)
        headers = {"Accept": "application/json"}
        if cached:
            headers |= cached.validators
        try:
            async with self._session.get(url, headers=headers, timeout=TIMEOUT) as resp:
                if resp.status == 304 and cached:
                    return cached.document, False
                if resp.status == 404:
                    raise StationNotFound(url)
                if resp.status == 429:
                    raise BshError(f"{url}: rate limited (HTTP 429)")
                resp.raise_for_status()
                document = await resp.json(content_type=None)
                # Prefer Last-Modified: Apache appends "-gzip" to the ETag of
                # compressed responses and then never matches If-None-Match.
                validators = {}
                if modified := resp.headers.get("Last-Modified"):
                    validators["If-Modified-Since"] = modified
                elif etag := resp.headers.get("ETag"):
                    validators["If-None-Match"] = etag
                self._cache[url] = _Cached(validators, document)
                return document, True
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise BshError(f"{url}: {error}") from error

    async def station_data(self) -> tuple[Any, bool]:
        """Measurements, automated forecast and metadata of the station."""
        return await self._get(STATION_URL.format(station=self.station))

    async def area_table(self, sea: str) -> tuple[Any, bool]:
        """Official forecast table of all areas of one sea."""
        return await self._get(AREA_URL.format(sea=sea))

    async def dmi_cube(
        self, west: float, south: float, east: float, north: float, step: str
    ) -> Any:
        """DMI model values of one time step in a bounding box."""
        url = (
            f"{DMI_URL}/cube?bbox={west:.4f},{south:.4f},{east:.4f},{north:.4f}"
            f"&datetime={step}&parameter-name={DMI_PARAMETER}&f=GeoJSON"
        )
        document, _ = await self._get(url)
        return document

    async def dmi_position(self, lon: float, lat: float) -> Any:
        """DMI model run at the node nearest to a position."""
        url = (
            f"{DMI_URL}/position?coords=POINT({lon:.5f}%20{lat:.5f})"
            f"&parameter-name={DMI_PARAMETER}&f=GeoJSON"
        )
        document, _ = await self._get(url)
        return document

    async def stations(self) -> Any:
        """All stations of the API (large, used by the config flow only)."""
        document, _ = await self._get(STATIONS_URL)
        return document
