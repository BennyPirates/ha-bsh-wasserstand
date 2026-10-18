"""Parse BSH water level API documents without Home Assistant dependencies."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class ParseError(Exception):
    """The BSH document did not have the expected structure."""


@dataclass(frozen=True, slots=True)
class Point:
    """One water level value in cm relative to NHN/SKN."""

    time: datetime
    value: float


@dataclass(frozen=True, slots=True)
class Period:
    """One period of the official area forecast."""

    label: str
    lower: int
    upper: int


@dataclass(frozen=True, slots=True)
class OfficialForecast:
    """Official forecast of the BSH water level service for one area."""

    area: str | None
    issued: datetime | None
    periods: list[Period]
    warning: str | None = None
    text: str | None = None


@dataclass(frozen=True, slots=True)
class Station:
    """Measurements and automated forecast of one gauge."""

    label: str
    area: str | None
    region: str | None
    observations: list[Point]
    forecast: list[Point]
    forecast_run: datetime | None
    references: dict[str, float]
    warning: str | None
    text: str | None
    longitude: float | None = None
    latitude: float | None = None


@dataclass(frozen=True, slots=True)
class DmiForecast:
    """DMI storm surge model run at one grid node."""

    longitude: float
    latitude: float
    distance_km: float
    points: list[Point]


@dataclass(frozen=True, slots=True)
class WindPoint:
    """Hourly wind in knots, direction in degrees (where it comes from)."""

    time: datetime
    speed: float
    gust: float | None
    direction: float | None


@dataclass(frozen=True, slots=True)
class WindForecast:
    """DWD observations and MOSMIX forecast near a position."""

    points: list[WindPoint]
    sources: list[str]


@dataclass(frozen=True, slots=True)
class WaterLevelData:
    """Combined result of one update."""

    station: Station | None
    official: OfficialForecast | None
    errors: list[str] = field(default_factory=list)
    dmi: DmiForecast | None = None
    wind: WindForecast | None = None


def _time(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError as error:
        raise ParseError(f"invalid timestamp {raw!r}") from error


def _number(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).replace("−", "-"))
    except ValueError:
        return None


def _text(raw: object) -> str | None:
    if isinstance(raw, dict):
        raw = raw.get("de") or raw.get("en")
    text = " ".join(str(raw or "").split())
    return text or None


def parse_station(document: dict[str, Any]) -> Station:
    """Parse one item of the WaterLevelForecast OGC API collection."""
    props = document.get("properties")
    if not isinstance(props, dict) or not isinstance(props.get("curve"), list):
        raise ParseError("station document without curve")

    # Curve values are cm above gauge zero; convert to NHN like the BSH pages.
    zero = _number(props.get("gaugezero_relative_to_nhn"))
    if zero is None:
        raise ParseError("gauge zero missing")

    observations: list[Point] = []
    forecast: list[Point] = []
    for entry in props["curve"]:
        time = _time(entry.get("timestamp"))
        if time is None:
            continue
        if (value := _number(entry.get("measurement"))) is not None:
            observations.append(Point(time, value + zero))
        if (value := _number(entry.get("automated_curve_forecast"))) is not None:
            forecast.append(Point(time, value + zero))

    references = {}
    for key, name in (("mean_high_water", "MHW"), ("mean_low_water", "MNW")):
        if (value := _number(props.get(key))) is not None:
            references[name] = value + zero

    return Station(
        label=str(props.get("gauge_label") or document.get("id") or ""),
        area=props.get("area"),
        region=props.get("region"),
        observations=sorted(observations, key=lambda p: p.time),
        forecast=sorted(forecast, key=lambda p: p.time),
        forecast_run=_time(props.get("automated_curveforecast_timestamp")),
        references=references,
        warning=props.get("official_warning_level_region"),
        text=_text(props.get("forecast_text")),
        longitude=_number(props.get("longitude")),
        latitude=_number(props.get("latitude")),
    )


def parse_official(document: dict[str, Any], area: str | None) -> OfficialForecast:
    """Parse the official period table of wasserstand.bsh.de/data/<sea>/map.json."""
    table = document.get("forecast_table")
    if not isinstance(table, dict):
        raise ParseError("no forecast table")
    areas = [f.get("area") for f in table.get("forecasts", [])]
    if area not in areas:
        raise ParseError(f"area {area!r} not in forecast table")
    index = areas.index(area)

    periods: list[Period] = []
    warning = None
    for period in table.get("periods", []):
        values = period.get("forecasts", [])
        if index >= len(values):
            continue
        low = _number(values[index].get("lower_limit"))
        high = _number(values[index].get("upper_limit"))
        if low is None or high is None:
            continue
        warning = warning or values[index].get("warning")
        low, high = sorted((int(low), int(high)))
        periods.append(Period(_text(period.get("title")) or "", low, high))

    return OfficialForecast(
        area=area,
        issued=_time(
            table.get("forecast_timestamp") or document.get("creation_forecast")
        ),
        periods=periods,
        warning=warning,
        text=_text(document.get("forecast_text")),
    )


def parse_stations(document: dict[str, Any]) -> dict[str, str]:
    """Map station id to label from the collection's item list."""
    stations = {}
    for feature in document.get("features", []):
        if feature.get("id"):
            label = (feature.get("properties") or {}).get("gauge_label")
            stations[str(feature["id"])] = str(label or feature["id"])
    return stations


def distance_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great circle distance."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _dmi_features(document: dict[str, Any]) -> list[tuple[float, float, Any]]:
    result = []
    for feature in document.get("features", []):
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) >= 2:
            result.append(
                (float(coords[0]), float(coords[1]), feature.get("properties") or {})
            )
    return result


def nearest_wet_node(
    document: dict[str, Any], lon: float, lat: float, parameter: str
) -> tuple[float, float] | None:
    """Nearest model node with a value in a DMI cube (GeoJSON) response."""
    wet = [
        (x, y)
        for x, y, props in _dmi_features(document)
        if props.get(parameter) is not None
    ]
    if not wet:
        return None
    return min(wet, key=lambda node: distance_km(lon, lat, node[0], node[1]))


def parse_dmi(
    document: dict[str, Any], lon: float, lat: float, parameter: str
) -> DmiForecast:
    """Parse a DMI position query (GeoJSON, metres) into cm NHN."""
    features = _dmi_features(document)
    points = [
        Point(_time(props.get("step")), float(props[parameter]) * 100)  # type: ignore[arg-type]
        for _, _, props in features
        if props.get(parameter) is not None and props.get("step")
    ]
    if not points:
        raise ParseError("DMI node has no water level values")
    node_lon, node_lat = features[0][0], features[0][1]
    return DmiForecast(
        longitude=node_lon,
        latitude=node_lat,
        distance_km=round(distance_km(lon, lat, node_lon, node_lat), 2),
        points=sorted(points, key=lambda p: p.time),
    )


KMH_PER_KNOT = 1.852


def parse_wind(document: dict[str, Any]) -> WindForecast:
    """Parse a Bright Sky weather response (km/h) into knots."""
    points = []
    for record in document.get("weather") or []:
        time, speed = _time(record.get("timestamp")), _number(record.get("wind_speed"))
        if time is None or speed is None:
            continue
        gust = _number(record.get("wind_gust_speed"))
        points.append(
            WindPoint(
                time=time,
                speed=round(speed / KMH_PER_KNOT, 1),
                gust=round(gust / KMH_PER_KNOT, 1) if gust is not None else None,
                direction=_number(record.get("wind_direction")),
            )
        )
    if not points:
        raise ParseError("no wind values")
    used = {record.get("source_id") for record in document.get("weather") or []}
    sources = [
        f"{source.get('station_name')} ({source.get('observation_type')})"
        for source in document.get("sources") or []
        if source.get("id") in used
    ]
    return WindForecast(sorted(points, key=lambda p: p.time), sources)
