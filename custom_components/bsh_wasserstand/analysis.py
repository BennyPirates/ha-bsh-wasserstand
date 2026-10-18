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


def hourly(points: list[Point]) -> list[Point]:
    """Keep full-hour points to make attributes compact."""
    return [p for p in points if p.time.minute == 0]


def model_series(
    data: WaterLevelData, model: str, bound: str | None = None
) -> list[Point]:
    """Central model line, or the lower/upper edge of its uncertainty band."""
    if data.figure is None or model not in data.figure.models:
        return []
    entry = data.figure.models[model]
    if bound is None:
        return entry.points
    return [Point(b.time, b.upper if bound == HIGH else b.lower) for b in entry.band]


def crossings(
    data: WaterLevelData,
    now: datetime,
    threshold: float,
    kind: str,
    use_band: bool,
    horizon: timedelta | None = None,
) -> list[Crossing]:
    """Collect every source that reaches the threshold in the horizon."""

    def hit(value: float) -> bool:
        return value >= threshold if kind == HIGH else value <= threshold

    found: list[Crossing] = []
    if data.figure and data.figure.observations:
        latest = data.figure.observations[-1]
        if hit(latest.value):
            found.append(Crossing("observation", latest, latest))

    for model in sorted(data.figure.models) if data.figure else []:
        sources = [(model, model_series(data, model))]
        if use_band:
            sources.append((f"{model}_band", model_series(data, model, kind)))
        for source, series in sources:
            hits = [p for p in upcoming(series, now, horizon) if hit(p.value)]
            if hits:
                found.append(Crossing(source, hits[0], extreme(hits, kind)))

    if data.official:
        for period in data.official.periods:
            value = period.upper if kind == HIGH else period.lower
            if hit(value):
                found.append(Crossing(f"official: {period.label}", None, None))
    return found
