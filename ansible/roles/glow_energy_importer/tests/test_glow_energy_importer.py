"""Unit tests for the glow_energy_importer tariff logic and the peak/off-peak,
standing/running split statistics.

Run from the role directory with no external dependencies:

    python3 -m unittest discover -s tests

The importer module imports requests/websocket/yaml at module scope (and evaluates
a `requests.Session` annotation at import time); those are network/IO concerns the
pure logic under test never touches, so they are stubbed before the module loads.
"""

import importlib.util
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# --- stub the network deps so the module imports with nothing installed ---------
_req = types.ModuleType("requests")


class _FakeSession:
    def __init__(self):
        self.headers = {}


_req.Session = _FakeSession
_req.RequestException = Exception
sys.modules.setdefault("requests", _req)

_ws = types.ModuleType("websocket")
_ws.WebSocketException = Exception
sys.modules.setdefault("websocket", _ws)

sys.modules.setdefault("yaml", types.ModuleType("yaml"))

# State must land somewhere writable and disposable; the module reads STATE_DIRECTORY
# once at import, so set it before loading.
_STATE = tempfile.mkdtemp(prefix="glow-test-state-")
import os  # noqa: E402

os.environ["STATE_DIRECTORY"] = _STATE

_MODULE_PATH = Path(__file__).resolve().parent.parent / "files" / "glow_energy_importer.py"
_spec = importlib.util.spec_from_file_location("glow_energy_importer", _MODULE_PATH)
gei = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gei)

LONDON = ZoneInfo("Europe/London")


class TariffTest(unittest.TestCase):
    def setUp(self):
        # A flat version, then a provider switch, then an EV peak/off-peak version.
        self.tariff = gei.Tariff(
            [
                {
                    "effective_from": "2025-01-01",
                    "standing_charge": 0.50,
                    "unit_rates": [{"rate": 0.25}],
                },
                {
                    "effective_from": "2026-07-08",
                    "standing_charge": 0.57,
                    "unit_rates": [
                        {"from": "23:00", "to": "06:00", "rate": 0.07, "band": "offpeak"},
                        {"from": "06:00", "to": "23:00", "rate": 0.30, "band": "peak"},
                    ],
                },
            ]
        )

    def _dt(self, s):
        return datetime.fromisoformat(s).replace(tzinfo=LONDON)

    def test_date_effective_version_selection(self):
        self.assertEqual(self.tariff.standing_charge(self._dt("2025-06-01T00:00").date()), 0.50)
        self.assertEqual(self.tariff.standing_charge(self._dt("2026-07-08T00:00").date()), 0.57)
        # The day before the switch still uses the old version.
        self.assertEqual(self.tariff.standing_charge(self._dt("2026-07-07T23:59").date()), 0.50)

    def test_no_version_before_first_effective_from(self):
        with self.assertRaises(ValueError):
            self.tariff.rate(self._dt("2024-12-31T12:00"))

    def test_flat_version_is_all_peak(self):
        for hour in (0, 6, 12, 23):
            dt = self._dt(f"2025-06-01T{hour:02d}:00")
            self.assertEqual(self.tariff.rate(dt), 0.25)
            self.assertEqual(self.tariff.band(dt), "peak")

    def test_ev_peak_offpeak_windows(self):
        cases = {
            "00:00": ("offpeak", 0.07),
            "05:30": ("offpeak", 0.07),
            "06:00": ("peak", 0.30),   # boundary: peak starts inclusive
            "22:30": ("peak", 0.30),
            "23:00": ("offpeak", 0.07),  # boundary: off-peak starts inclusive
            "23:30": ("offpeak", 0.07),
        }
        for hm, (band, rate) in cases.items():
            dt = self._dt(f"2026-07-10T{hm}")
            self.assertEqual(self.tariff.band(dt), band, hm)
            self.assertEqual(self.tariff.rate(dt), rate, hm)

    def test_band_partition_is_total_over_a_day(self):
        # Every half-hour of an EV-tariff day is peak xor off-peak, and the off-peak
        # window (23:00-06:00) is exactly 7 hours = 14 half-hour slots.
        offpeak = 0
        for slot in range(48):
            dt = self._dt("2026-07-10T00:00") + timedelta(minutes=30 * slot)
            band = self.tariff.band(dt)
            self.assertIn(band, ("peak", "offpeak"))
            if band == "offpeak":
                offpeak += 1
        self.assertEqual(offpeak, 14)


class SplitStatisticsInvariantTest(unittest.TestCase):
    """Drive a full import with synthetic readings and a network-free Importer, then
    assert the split series reconcile against the two base totals."""

    def setUp(self):
        # The import checkpoint is a shared module-level file; a stale checkpoint
        # from another test would make this run import nothing.
        gei.IMPORT_STATE.unlink(missing_ok=True)

    def _importer(self):
        config = {
            "glow": {
                "url": "http://glow.invalid",
                "application_id": "x",
                "username": "u",
                "password": "p",
            },
            "ha": {"url": "http://ha.invalid", "token": "t"},
            "backfill_days": 30,
            # One always-on TOU version so the split is exercised regardless of date.
            "tariffs": [
                {
                    "effective_from": "2000-01-01",
                    "standing_charge": 0.60,
                    "unit_rates": [
                        {"from": "23:00", "to": "06:00", "rate": 0.10, "band": "offpeak"},
                        {"from": "06:00", "to": "23:00", "rate": 0.30, "band": "peak"},
                    ],
                }
            ],
        }
        imp = gei.Importer(config)
        imp.resource_id = "r"
        return imp

    def _one_full_day_rows(self):
        # A complete day well past the settle horizon so every hour imports.
        day = (datetime.now(LONDON) - timedelta(days=10)).date()
        midnight = datetime.combine(day, datetime.min.time(), tzinfo=LONDON)
        start = int(midnight.astimezone(timezone.utc).timestamp())
        return [(start + i * gei.HALF_HOUR, 0.5) for i in range(48)]

    def test_partitions_reconcile_with_totals(self):
        imp = self._importer()
        rows = self._one_full_day_rows()
        imp.glow.half_hourly = lambda resource, frm, to: rows

        captured = {}
        imp.ha.import_statistics = lambda metadata, stats: captured.__setitem__(
            metadata["statistic_id"], stats
        )

        imp._run_import()

        def final(statistic_id):
            return captured[statistic_id][-1]["sum"]

        cid = imp.consumption_id
        # 14 off-peak slots x 0.5 kWh = 7; 34 peak slots x 0.5 = 17; total 24.
        self.assertAlmostEqual(final(cid), 24.0, places=3)
        self.assertAlmostEqual(final(imp.consumption_peak_id), 17.0, places=3)
        self.assertAlmostEqual(final(imp.consumption_offpeak_id), 7.0, places=3)
        self.assertAlmostEqual(
            final(imp.consumption_peak_id) + final(imp.consumption_offpeak_id),
            final(cid),
            places=3,
        )

        # Running: 17 x 0.30 + 7 x 0.10 = 5.8; standing: 0.60; total 6.4.
        cost = imp.cost_id
        self.assertAlmostEqual(final(cost), 6.4, places=3)
        self.assertAlmostEqual(final(imp.cost_standing_id), 0.60, places=3)
        self.assertAlmostEqual(final(imp.cost_peak_id), 5.1, places=3)
        self.assertAlmostEqual(final(imp.cost_offpeak_id), 0.7, places=3)
        self.assertAlmostEqual(
            final(imp.cost_standing_id) + final(imp.cost_peak_id) + final(imp.cost_offpeak_id),
            final(cost),
            places=3,
        )


class DccCostTest(unittest.TestCase):
    """The DCC-sourced cost series reads its own resource (pence) and converts to
    GBP, independent of the local tariff pricing."""

    def setUp(self):
        gei.IMPORT_STATE.unlink(missing_ok=True)

    def _one_full_day(self):
        day = (datetime.now(LONDON) - timedelta(days=10)).date()
        midnight = datetime.combine(day, datetime.min.time(), tzinfo=LONDON)
        return int(midnight.astimezone(timezone.utc).timestamp())

    def _importer(self, dcc_cost=True):
        config = {
            "glow": {"url": "http://x", "application_id": "x", "username": "u", "password": "p"},
            "ha": {"url": "http://x", "token": "t"},
            "backfill_days": 30,
            "dcc_cost": dcc_cost,
            "tariffs": [
                {
                    "effective_from": "2000-01-01",
                    "standing_charge": 0.60,
                    "unit_rates": [{"rate": 0.30, "band": "peak"}],
                }
            ],
        }
        imp = gei.Importer(config)
        imp.resource_id = "cons"
        return imp

    def test_dcc_cost_converts_pence_to_gbp(self):
        imp = self._importer(dcc_cost=True)
        imp.cost_resource_id = "cost"
        start = self._one_full_day()
        cons_rows = [(start + i * gei.HALF_HOUR, 0.5) for i in range(48)]
        # 10 pence per half-hour x 48 = 480 pence = GBP 4.80.
        cost_rows = [(start + i * gei.HALF_HOUR, 10.0) for i in range(48)]
        imp.glow.half_hourly = lambda resource, frm, to: (
            cost_rows if resource == "cost" else cons_rows
        )
        captured = {}
        imp.ha.import_statistics = lambda metadata, stats: captured.__setitem__(
            metadata["statistic_id"], stats
        )

        imp._run_import()

        self.assertIn(imp.cost_dcc_id, captured)
        self.assertAlmostEqual(captured[imp.cost_dcc_id][-1]["sum"], 4.80, places=3)
        # DCC cost is unit-only: it must not carry the standing charge that the
        # local total cost does.
        self.assertLess(captured[imp.cost_dcc_id][-1]["sum"], captured[imp.cost_id][-1]["sum"])

    def test_dcc_cost_disabled_emits_no_series(self):
        imp = self._importer(dcc_cost=False)
        imp.cost_resource_id = "cost"  # present, but the toggle is off
        start = self._one_full_day()
        cons_rows = [(start + i * gei.HALF_HOUR, 0.5) for i in range(48)]
        imp.glow.half_hourly = lambda resource, frm, to: cons_rows
        captured = {}
        imp.ha.import_statistics = lambda metadata, stats: captured.__setitem__(
            metadata["statistic_id"], stats
        )

        imp._run_import()

        self.assertNotIn(imp.cost_dcc_id, captured)


if __name__ == "__main__":
    unittest.main()
