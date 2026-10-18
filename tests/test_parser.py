"""Tests for the Home Assistant independent parser and analysis modules."""

from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"

# Import the pure modules without executing the Home Assistant package __init__.
_package = types.ModuleType("bsh_pure")
_package.__path__ = [str(ROOT / "custom_components" / "bsh_wasserstand")]
sys.modules["bsh_pure"] = _package
parser = importlib.import_module("bsh_pure.parser")
analysis = importlib.import_module("bsh_pure.analysis")

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 10, 18, 9, 30, tzinfo=BERLIN)


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


def load_data():
    station = parser.parse_station(fixture("travemuende.json"))
    official = parser.parse_official(fixture("ostsee-map.json"), station.area)
    return parser.WaterLevelData(station, official)


class StationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.station = load_data().station

    def test_metadata(self) -> None:
        self.assertEqual(self.station.label, "Travemünde")
        self.assertEqual(self.station.area, "Lübecker Bucht")
        self.assertEqual(self.station.region, "baltic_sea")
        self.assertEqual(self.station.warning, "Sturmflut")

    def test_values_are_relative_to_nhn(self) -> None:
        first = self.station.observations[0]
        self.assertEqual(first.time, datetime(2026, 10, 17, 12, 0, tzinfo=BERLIN))
        self.assertEqual(first.value, 558 - 502)
        self.assertEqual(self.station.references, {"MHW": 128.0, "MNW": -116.0})

    def test_curve_split(self) -> None:
        self.assertEqual(len(self.station.observations), 86)
        self.assertEqual(len(self.station.forecast), 251)
        self.assertLess(
            self.station.observations[-1].time, self.station.forecast[0].time
        )
        self.assertEqual(
            self.station.forecast_run,
            datetime(2026, 10, 18, 9, 35, 4, tzinfo=BERLIN),
        )

    def test_missing_curve(self) -> None:
        with self.assertRaises(parser.ParseError):
            parser.parse_station({"properties": {}})


class OfficialTest(unittest.TestCase):
    def test_table(self) -> None:
        official = load_data().official
        self.assertEqual(official.area, "Lübecker Bucht")
        self.assertEqual(
            official.issued, datetime(2026, 10, 18, 7, 45, 6, tzinfo=BERLIN)
        )
        self.assertEqual(official.warning, "Sturmflut")
        self.assertEqual(
            [(p.label, p.lower, p.upper) for p in official.periods],
            [
                ("Bis Sonntag Abend", 35, 115),
                ("Sonntag in der Nacht", 30, 65),
                ("Montag im Tagesverlauf", 30, 55),
            ],
        )

    def test_unknown_area(self) -> None:
        with self.assertRaises(parser.ParseError):
            parser.parse_official(fixture("ostsee-map.json"), "Nordfriesland")

    def test_negative_values(self) -> None:
        document = {
            "forecast_table": {
                "forecasts": [{"area": "A"}],
                "periods": [
                    {
                        "title": {"de": "Montag"},
                        "forecasts": [{"lower_limit": "−60", "upper_limit": "-35"}],
                    }
                ],
            }
        }
        period = parser.parse_official(document, "A").periods[0]
        self.assertEqual((period.lower, period.upper), (-60, -35))


class AnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_data()

    def test_upcoming_extreme(self) -> None:
        future = analysis.upcoming(self.data.station.forecast, NOW, timedelta(hours=72))
        self.assertTrue(all(NOW <= p.time <= NOW + timedelta(hours=72) for p in future))
        high = analysis.extreme(future, analysis.HIGH)
        low = analysis.extreme(future, analysis.LOW)
        self.assertGreater(high.value, low.value)

    def test_high_threshold(self) -> None:
        found = analysis.crossings(self.data, NOW, 100, analysis.HIGH)
        sources = {c.source for c in found}
        self.assertIn("observation", sources)
        self.assertIn("official: Bis Sonntag Abend", sources)

    def test_no_crossing(self) -> None:
        self.assertEqual(analysis.crossings(self.data, NOW, 300, analysis.HIGH), [])


class AlertLevelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_data()

    def level(self, **thresholds: float) -> str:
        values = {"high": 300, "high_pre": 300, "low": -300, "low_pre": -300}
        values.update(thresholds)
        return analysis.alert_level(self.data, NOW, values, analysis.HIGH)[0]

    def test_none(self) -> None:
        self.assertEqual(self.level(), analysis.NONE)

    def test_prewarning(self) -> None:
        self.assertEqual(self.level(high_pre=110), analysis.PREWARNING)

    def test_warning_wins(self) -> None:
        self.assertEqual(self.level(high=110, high_pre=90), analysis.WARNING)

    def test_low_side(self) -> None:
        values = {"high": 300, "high_pre": 300, "low": 0, "low_pre": 35}
        level, threshold, found = analysis.alert_level(
            self.data, NOW, values, analysis.LOW
        )
        self.assertEqual((level, threshold), (analysis.PREWARNING, 35))
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
