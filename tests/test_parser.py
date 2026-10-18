"""Tests for the Home Assistant independent parser and analysis modules."""

from __future__ import annotations

import importlib
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
NOW = datetime(2026, 10, 18, 9, 0, tzinfo=BERLIN)


def load_data():
    figure = parser.parse_figure((FIXTURES / "travemuende-figure.html").read_text())
    official = parser.parse_official((FIXTURES / "travemuende.html").read_text())
    return parser.WaterLevelData(figure, official)


class FigureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.figure = load_data().figure

    def test_observations(self) -> None:
        latest = self.figure.observations[-1]
        self.assertEqual(latest.time, datetime(2026, 10, 18, 8, 54, tzinfo=BERLIN))
        self.assertEqual(latest.value, 105.0)
        self.assertEqual(len(self.figure.observations), 2867)

    def test_models_and_bands(self) -> None:
        self.assertEqual(set(self.figure.models), {"bsh", "dmi"})
        bsh = self.figure.models["bsh"]
        self.assertEqual(bsh.run, "18.10.2026 00UTC")
        self.assertEqual(len(bsh.points), len(bsh.band))
        for point, band in zip(bsh.points, bsh.band, strict=True):
            self.assertEqual(point.time, band.time)
            self.assertLessEqual(band.lower, band.upper)

    def test_references(self) -> None:
        self.assertEqual(self.figure.references, {"MW": 7.0, "MHW": 128.0})

    def test_missing_figure(self) -> None:
        with self.assertRaises(parser.ParseError):
            parser.parse_figure("<html>Plotly.newPlot(gd, x)</html>")


class OfficialTest(unittest.TestCase):
    def test_table(self) -> None:
        official = load_data().official
        self.assertEqual(official.station, "Travemünde")
        self.assertEqual(official.area, "Lübecker Bucht")
        self.assertEqual(official.issued, datetime(2026, 10, 18, 7, 45, tzinfo=BERLIN))
        self.assertEqual(
            [(p.label, p.lower, p.upper) for p in official.periods],
            [
                ("Bis Sonntag Abend", 35, 115),
                ("Sonntag in der Nacht", 30, 65),
                ("Montag im Tagesverlauf", 30, 55),
            ],
        )

    def test_negative_values(self) -> None:
        page = (
            '<table class="table scheitelwerte"><tbody><tr><td>Montag</td>'
            "<td>−60 cm bis −35 cm</td></tr></tbody></table>"
        )
        official = parser.parse_official(page)
        self.assertEqual(official.periods[0].lower, -60)
        self.assertEqual(official.periods[0].upper, -35)


class AnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_data()

    def test_upcoming_extreme(self) -> None:
        series = analysis.model_series(self.data, "bsh")
        future = analysis.upcoming(series, NOW, timedelta(hours=72))
        self.assertTrue(all(NOW <= p.time <= NOW + timedelta(hours=72) for p in future))
        high = analysis.extreme(future, analysis.HIGH)
        low = analysis.extreme(future, analysis.LOW)
        self.assertGreater(high.value, low.value)

    def test_high_threshold(self) -> None:
        found = analysis.crossings(self.data, NOW, 100, analysis.HIGH, True)
        sources = {c.source for c in found}
        self.assertIn("observation", sources)
        self.assertIn("official: Bis Sonntag Abend", sources)

    def test_no_crossing(self) -> None:
        found = analysis.crossings(self.data, NOW, 300, analysis.HIGH, True)
        self.assertEqual(found, [])

    def test_band_is_more_conservative(self) -> None:
        later = NOW + timedelta(days=2)
        without = analysis.crossings(self.data, later, 0, analysis.LOW, False)
        with_band = analysis.crossings(self.data, later, 0, analysis.LOW, True)
        self.assertGreaterEqual(len(with_band), len(without))
        self.assertTrue(any(c.source.endswith("_band") for c in with_band))


if __name__ == "__main__":
    unittest.main()
