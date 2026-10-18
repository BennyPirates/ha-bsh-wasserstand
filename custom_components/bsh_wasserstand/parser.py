"""Parse BSH water level pages without Home Assistant dependencies."""

from __future__ import annotations

import base64
import html
import json
import math
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")

_NEW_PLOT = re.compile(r'Plotly\.newPlot\(\s*"[^"]+",\s*')
_REFERENCE = re.compile(r"\(([A-Z]{2,5})\)\s*$")
_RANGE = re.compile(r"([+\-−]?\s*\d+)\s*cm\s*bis\s*([+\-−]?\s*\d+)\s*cm")
_TABLE = re.compile(r"<table[^>]*scheitelwerte[^>]*>(.*?)</table>", re.S)
_ROW = re.compile(r"<tr>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>", re.S)
_ISSUED = re.compile(
    r"Vorhersage erstellt am:[^0-9]*(\d{2}\.\d{2}\.\d{4}),\s*(\d{2}:\d{2})"
)
_AREA = re.compile(r'Vorhersage für das Gebiet\s*"([^"]+)"')
_STATION = re.compile(r'<span class="pegel-name">([^<]+)</span>')
_INFOBOX = re.compile(r'<p class="infobox"[^>]*>(.*?)</p>', re.S)
_TAG = re.compile(r"<[^>]+>")

_DTYPES = {
    "f4": "f",
    "f8": "d",
    "i1": "b",
    "u1": "B",
    "i2": "h",
    "u2": "H",
    "i4": "i",
    "u4": "I",
}


class ParseError(Exception):
    """The BSH page did not have the expected structure."""


@dataclass(frozen=True, slots=True)
class Point:
    """One water level value in cm relative to NHN/SKN."""

    time: datetime
    value: float


@dataclass(frozen=True, slots=True)
class BandPoint:
    """Uncertainty range of a model forecast."""

    time: datetime
    lower: float
    upper: float


@dataclass(frozen=True, slots=True)
class Model:
    """One model run with its uncertainty band."""

    run: str
    points: list[Point]
    band: list[BandPoint]


@dataclass(frozen=True, slots=True)
class FigureData:
    """Data contained in the interactive BSH figure."""

    observations: list[Point]
    models: dict[str, Model]
    references: dict[str, float]


@dataclass(frozen=True, slots=True)
class Period:
    """One row of the official BSH forecast table."""

    label: str
    lower: int
    upper: int


@dataclass(frozen=True, slots=True)
class OfficialForecast:
    """Official forecast text published by the BSH water level service."""

    station: str | None
    area: str | None
    issued: datetime | None
    periods: list[Period]
    notice: str | None = None


@dataclass(frozen=True, slots=True)
class WaterLevelData:
    """Combined result of one update."""

    figure: FigureData | None
    official: OfficialForecast | None
    errors: list[str] = field(default_factory=list)


def _text(fragment: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", fragment)).split())


def _values(raw: object) -> list[float]:
    if isinstance(raw, list):
        return [math.nan if v is None else float(v) for v in raw]
    if isinstance(raw, dict) and "bdata" in raw:
        code = _DTYPES.get(str(raw.get("dtype")))
        if code is None:
            raise ParseError(f"unsupported dtype {raw.get('dtype')}")
        blob = base64.b64decode(str(raw["bdata"]))
        count = len(blob) // struct.calcsize(code)
        return [float(v) for v in struct.unpack(f"<{count}{code}", blob)]
    raise ParseError("unsupported value array")


def _points(times: list[str], values: list[float]) -> list[Point]:
    return [
        Point(datetime.fromisoformat(t), v)
        for t, v in zip(times, values, strict=False)
        if not math.isnan(v)
    ]


def _band(times: list[str], values: list[float]) -> list[BandPoint]:
    """Convert a closed polygon (forward edge, reversed edge) into a band."""
    half = len(times) // 2
    forward = _points(times[:half], values[:half])
    backward = {p.time: p.value for p in _points(times[half:], values[half:])}
    return [
        BandPoint(
            p.time, min(p.value, backward[p.time]), max(p.value, backward[p.time])
        )
        for p in forward
        if p.time in backward
    ]


def parse_figure(page: str) -> FigureData:
    """Extract the traces of the Plotly figure."""
    match = _NEW_PLOT.search(page)
    if match is None:
        raise ParseError("Plotly figure not found")
    try:
        traces, _ = json.JSONDecoder().raw_decode(page, match.end())
    except ValueError as error:
        raise ParseError(f"invalid figure data: {error}") from error
    if not isinstance(traces, list):
        raise ParseError("figure data is not a list")

    observations: list[Point] = []
    runs: dict[str, str] = {}
    lines: dict[str, list[Point]] = {}
    bands: dict[str, list[BandPoint]] = {}
    references: dict[str, float] = {}

    for trace in traces:
        name = str(trace.get("name") or "")
        times = trace.get("x")
        if not isinstance(times, list):
            continue
        values = _values(trace.get("y"))
        if name.startswith("Beobachtung"):
            observations = _points(times, values)
        elif " Lauf:" in name:
            key = name.split(" ", 1)[0].lower()
            runs[key] = name.split("Lauf:", 1)[1].strip()
            lines[key] = _points(times, values)
        elif name.endswith("-Spanne"):
            bands[name.split("-", 1)[0].lower()] = _band(times, values)
        elif (ref := _REFERENCE.search(name)) and values:
            references[ref.group(1)] = values[0]

    if not observations and not lines:
        raise ParseError("no water level traces found")
    models = {
        key: Model(run=runs[key], points=points, band=bands.get(key, []))
        for key, points in lines.items()
    }
    return FigureData(observations=observations, models=models, references=references)


def _cm(raw: str) -> int:
    return int(raw.replace("−", "-").replace(" ", ""))


def parse_official(page: str) -> OfficialForecast:
    """Extract the official forecast table from the station page."""
    periods: list[Period] = []
    if table := _TABLE.search(page):
        for label, value in _ROW.findall(table.group(1)):
            if span := _RANGE.search(_text(value)):
                low, high = sorted((_cm(span.group(1)), _cm(span.group(2))))
                periods.append(Period(_text(label), low, high))

    issued = None
    if found := _ISSUED.search(page):
        issued = datetime.strptime(
            f"{found.group(1)} {found.group(2)}", "%d.%m.%Y %H:%M"
        ).replace(tzinfo=BERLIN)

    area = _AREA.search(html.unescape(page))
    station = _STATION.search(page)
    notice = _INFOBOX.search(page)
    notice_text = _text(notice.group(1)) if notice else ""

    if not periods and issued is None:
        raise ParseError("official forecast table not found")
    return OfficialForecast(
        station=_text(station.group(1)) if station else None,
        area=" ".join(area.group(1).split()) if area else None,
        issued=issued,
        periods=periods,
        notice=notice_text or None,
    )
