"""HTTP client for the BSH water level pages."""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp

from .const import FIGURE_URL, STATION_URL

TIMEOUT = aiohttp.ClientTimeout(total=60)


class BshError(Exception):
    """The BSH service could not be reached."""


class StationNotFound(BshError):
    """The station page does not exist."""


@dataclass(slots=True)
class _Cached:
    validators: dict[str, str]
    body: str


class BshClient:
    """Download station pages, reusing unchanged documents via HTTP validators."""

    def __init__(self, session: aiohttp.ClientSession, station: str) -> None:
        self._session = session
        self.station = station
        self._cache: dict[str, _Cached] = {}

    async def _get(self, url: str) -> tuple[str, bool]:
        """Return the document and whether it changed since the last call."""
        cached = self._cache.get(url)
        headers = cached.validators if cached else {}
        try:
            async with self._session.get(url, headers=headers, timeout=TIMEOUT) as resp:
                if resp.status == 304 and cached:
                    return cached.body, False
                if resp.status == 404:
                    raise StationNotFound(url)
                resp.raise_for_status()
                body = await resp.text(encoding="utf-8", errors="replace")
                # Only Last-Modified: Apache appends "-gzip" to the ETag of
                # compressed responses and then never matches If-None-Match.
                validators = {}
                if modified := resp.headers.get("Last-Modified"):
                    validators["If-Modified-Since"] = modified
                self._cache[url] = _Cached(validators, body)
                return body, True
        except (aiohttp.ClientError, TimeoutError) as error:
            raise BshError(f"{url}: {error}") from error

    async def station_page(self) -> tuple[str, bool]:
        """Station page with the official forecast table."""
        return await self._get(STATION_URL.format(station=self.station))

    async def figure_page(self) -> tuple[str, bool]:
        """Interactive figure containing measurements and model runs (~5 MB)."""
        return await self._get(FIGURE_URL.format(station=self.station))
