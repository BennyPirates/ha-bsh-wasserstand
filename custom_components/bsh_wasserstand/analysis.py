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

    if data.official:
        for period in data.official.periods:
            value = period.upper if kind == HIGH else period.lower
            if hit(value):
                found.append(Crossing(f"official: {period.label}", None, None))
    return found
