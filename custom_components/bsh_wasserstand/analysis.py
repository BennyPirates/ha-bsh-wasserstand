"""Evaluate forecasts against the current time and alert thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .parser import Point, WaterLevelData

HIGH = "high"
LOW = "low"


@dataclass(frozen=True, slots=True)
class Crossing:
    """A forecast or observation that reaches an alert threshold."""

    source: str
    first: Point | None
    extreme: Point | None
    label: str | None = None
    value: float | None = None


def upcoming(
    points: list[Point], now: datetime, horizon: timedelta | None = None
) -> list[Point]:
    """Return points from now on, optionally limited to a horizon."""
    end = now + horizon if horizon else None
    return [p for p in points if p.time >= now and (end is None or p.time <= end)]


def extreme(points: list[Point], kind: str) -> Point | None:
    """Highest or lowest point."""
    if not points:
        return None
    pick = max if kind == HIGH else min
    return pick(points, key=lambda p: p.value)


def crossings(
    data: WaterLevelData,
    now: datetime,
    threshold: float,
    kind: str,
    horizon: timedelta | None = None,
) -> list[Crossing]:
    """Collect every source that reaches the threshold in the horizon."""

    def hit(value: float) -> bool:
        return value >= threshold if kind == HIGH else value <= threshold

    found: list[Crossing] = []
    station = data.station
    if station and station.observations:
        latest = station.observations[-1]
        if hit(latest.value):
            found.append(Crossing("observation", latest, latest))

    if station:
        hits = [p for p in upcoming(station.forecast, now, horizon) if hit(p.value)]
        if hits:
            found.append(Crossing("forecast", hits[0], extreme(hits, kind)))

    # The official ranges are too coarse for alerts (a period also covers
    # hours that are already over); they are shown as information only.
    return found


NONE = "none"
PREWARNING = "prewarning"
WARNING = "warning"
LEVELS = [NONE, PREWARNING, WARNING]


HYSTERESIS = 5.0


def alert_level(
    data: WaterLevelData,
    now: datetime,
    thresholds: dict[str, float],
    kind: str,
    horizon: timedelta | None = None,
    previous: str | None = None,
    hysteresis: float = HYSTERESIS,
) -> tuple[str, float | None, list[Crossing]]:
    """Highest alert level reached, its threshold and the sources reaching it.

    A level only drops once no source is within `hysteresis` cm of its
    threshold any more, so values around a threshold do not flap.
    """
    levels = ((WARNING, kind), (PREWARNING, f"{kind}_pre"))
    for level, key in levels:
        threshold = thresholds[key]
        if found := crossings(data, now, threshold, kind, horizon):
            return level, threshold, found
        if level == previous:
            relaxed = threshold - hysteresis if kind == HIGH else threshold + hysteresis
            if found := crossings(data, now, relaxed, kind, horizon):
                return level, threshold, found
    return NONE, None, []


def describe(found: list[Crossing], kind: str) -> dict[str, object]:
    """Common attributes: first time the threshold is reached and the peak."""
    timed = [c for c in found if c.first]
    first = min(timed, key=lambda c: c.first.time) if timed else None  # type: ignore[union-attr]
    peaks = [c.extreme for c in found if c.extreme]
    pick = max if kind == HIGH else min
    peak = pick(peaks, key=lambda p: p.value) if peaks else None
    return {
        "sources": [c.source for c in found],
        "first_time": first.first.time.isoformat() if first and first.first else None,
        "first_source": first.source if first else None,
        "peak": round(peak.value, 1) if peak else None,
        "peak_time": peak.time.isoformat() if peak else None,
        "details": [
            {
                "source": c.source,
                "first_time": c.first.time.isoformat() if c.first else None,
                "peak": round(c.extreme.value, 1) if c.extreme else c.value,
                "peak_time": c.extreme.time.isoformat() if c.extreme else None,
                "label": c.label,
            }
            for c in found
        ],
    }
