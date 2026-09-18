"""Unit tests for the foxess_mqtt_bridge pure logic: request signing, the data
timestamp parser, and the state mapping with its lifetime-counter guard.

Run from the role directory with no external dependencies:

    python3 -m unittest discover -s tests

The bridge imports paho/requests/yaml at module scope; those are network/IO
concerns the logic under test never touches, so they are stubbed before the
module loads.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path

_paho = types.ModuleType("paho")
_paho_mqtt = types.ModuleType("paho.mqtt")
_paho_client = types.ModuleType("paho.mqtt.client")
_paho.mqtt = _paho_mqtt
_paho_mqtt.client = _paho_client
sys.modules.setdefault("paho", _paho)
sys.modules.setdefault("paho.mqtt", _paho_mqtt)
sys.modules.setdefault("paho.mqtt.client", _paho_client)

_req = types.ModuleType("requests")
_req.RequestException = Exception
sys.modules.setdefault("requests", _req)

sys.modules.setdefault("yaml", types.ModuleType("yaml"))

_spec = importlib.util.spec_from_file_location(
    "foxess_mqtt_bridge",
    Path(__file__).resolve().parent.parent / "files" / "foxess_mqtt_bridge.py",
)
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)


class SignatureTest(unittest.TestCase):
    def test_joins_fields_with_literal_backslash_sequences(self):
        import hashlib

        expected = hashlib.md5(
            b"/op/v0/device/list\\r\\ntoken\\r\\n1700000000000"
        ).hexdigest()
        self.assertEqual(
            bridge.signature("/op/v0/device/list", "token", "1700000000000"), expected
        )

    def test_is_not_a_real_crlf(self):
        import hashlib

        crlf = hashlib.md5(b"/p\r\nt\r\n1").hexdigest()
        self.assertNotEqual(bridge.signature("/p", "t", "1"), crlf)


class ParseDataTimeTest(unittest.TestCase):
    def test_summer_time(self):
        self.assertEqual(
            bridge.parse_data_time("2026-09-18 16:01:10 BST+0100"),
            "2026-09-18T16:01:10+0100",
        )

    def test_winter_time(self):
        self.assertEqual(
            bridge.parse_data_time("2026-12-01 08:30:00 GMT+0000"),
            "2026-12-01T08:30:00+0000",
        )

    def test_unparseable_is_none(self):
        self.assertIsNone(bridge.parse_data_time("yesterday"))
        self.assertIsNone(bridge.parse_data_time(""))
        self.assertIsNone(bridge.parse_data_time(None))


def _datas(**values):
    return [{"variable": k, "value": v} for k, v in values.items()]


class BuildStateTest(unittest.TestCase):
    def test_maps_variables_to_keys(self):
        state = bridge.build_state(
            _datas(pvPower=2.2, SoC=65.0, batStatusV2="Discharge", unknownVar=1), {}
        )
        self.assertEqual(
            state, {"pv_power": 2.2, "battery_soc": 65.0, "battery_status": "Discharge"}
        )

    def test_float_noise_is_rounded(self):
        state = bridge.build_state(_datas(pvPower=0.10400000000000001), {})
        self.assertEqual(state["pv_power"], 0.104)

    def test_missing_and_blank_values_are_omitted(self):
        state = bridge.build_state(_datas(pvPower=None, loadsPower=""), {})
        self.assertEqual(state, {})

    def test_counter_going_backwards_is_held(self):
        totals = {}
        bridge.build_state(_datas(PVEnergyTotal=5.1), totals)
        state = bridge.build_state(_datas(PVEnergyTotal=0.0), totals)
        self.assertEqual(state["pv_energy"], 5.1)
        state = bridge.build_state(_datas(PVEnergyTotal=5.3), totals)
        self.assertEqual(state["pv_energy"], 5.3)

    def test_measurements_may_fall(self):
        totals = {}
        bridge.build_state(_datas(pvPower=2.2), totals)
        state = bridge.build_state(_datas(pvPower=0.0), totals)
        self.assertEqual(state["pv_power"], 0.0)

    def test_numeric_strings_are_coerced(self):
        state = bridge.build_state(_datas(batCycleCount="3", currentFaultCount="0"), {})
        self.assertEqual(state, {"battery_cycles": 3, "fault_count": 0})

    def test_non_numeric_counter_is_dropped(self):
        state = bridge.build_state(_datas(feedin="n/a"), {})
        self.assertNotIn("grid_export_energy", state)

    def test_sensor_keys_are_unique(self):
        keys = [sensor[1] for sensor in bridge.SENSORS]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
