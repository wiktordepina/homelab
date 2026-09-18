#!/usr/bin/env python3
"""foxess_mqtt_bridge — periodic poller that republishes a FoxESS inverter's
real-time data from the FoxESS Cloud Open API to MQTT with Home Assistant
discovery.

One `device/real/query` call per tick returns every variable the inverter
reports, so the whole device costs a single call against the Open API's daily
quota. The state payload carries the cloud's own data timestamp as
`last_update`: the datalogger uploads on its own schedule, so that — not the
poll time — is how fresh the readings really are.
"""

import hashlib
import json
import logging
import os
import re
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
import requests
import yaml

CONFIG_PATH = Path(
    os.environ.get("FOXESS_MQTT_BRIDGE_CONFIG", "/etc/foxess-mqtt-bridge/config.yml")
)

ERRNO_RATE_LIMITED = 40400
RATE_LIMIT_BACKOFF = 900

# (api variable, key, name, unit, device_class, state_class)
SENSORS = [
    # Live power. Every flow is its own non-negative series; the two signed
    # series are for power-flow cards that want one entity per node.
    ("pvPower", "pv_power", "PV Power", "kW", "power", "measurement"),
    ("pv1Power", "pv1_power", "PV1 Power", "kW", "power", "measurement"),
    ("pv2Power", "pv2_power", "PV2 Power", "kW", "power", "measurement"),
    ("loadsPower", "load_power", "Load Power", "kW", "power", "measurement"),
    ("gridConsumptionPower", "grid_import_power", "Grid Import Power", "kW", "power", "measurement"),
    ("feedinPower", "grid_export_power", "Grid Export Power", "kW", "power", "measurement"),
    ("meterPower", "grid_power", "Grid Power", "kW", "power", "measurement"),
    ("batChargePower", "battery_charge_power", "Battery Charge Power", "kW", "power", "measurement"),
    ("batDischargePower", "battery_discharge_power", "Battery Discharge Power", "kW", "power", "measurement"),
    ("invBatPower", "battery_power", "Battery Power", "kW", "power", "measurement"),
    ("generationPower", "inverter_power", "Inverter Output Power", "kW", "power", "measurement"),
    ("epsPower", "eps_power", "EPS Power", "kW", "power", "measurement"),
    # Lifetime energy counters
    ("PVEnergyTotal", "pv_energy", "PV Energy", "kWh", "energy", "total_increasing"),
    ("gridConsumption", "grid_import_energy", "Grid Import Energy", "kWh", "energy", "total_increasing"),
    ("feedin", "grid_export_energy", "Grid Export Energy", "kWh", "energy", "total_increasing"),
    ("chargeEnergyToTal", "battery_charge_energy", "Battery Charge Energy", "kWh", "energy", "total_increasing"),
    ("dischargeEnergyToTal", "battery_discharge_energy", "Battery Discharge Energy", "kWh", "energy", "total_increasing"),
    ("loads", "load_energy", "Load Energy", "kWh", "energy", "total_increasing"),
    ("generation", "inverter_energy", "Inverter Output Energy", "kWh", "energy", "total_increasing"),
    # Battery
    ("SoC", "battery_soc", "Battery SoC", "%", "battery", "measurement"),
    ("SOH", "battery_soh", "Battery SoH", "%", None, "measurement"),
    ("batTemperature", "battery_temperature", "Battery Temperature", "°C", "temperature", "measurement"),
    ("batVolt", "battery_voltage", "Battery Voltage", "V", "voltage", "measurement"),
    ("batCycleCount", "battery_cycles", "Battery Cycle Count", None, None, "total_increasing"),
    ("batStatusV2", "battery_status", "Battery Status", None, None, None),
    # Inverter / grid
    ("invTemperation", "inverter_temperature", "Inverter Temperature", "°C", "temperature", "measurement"),
    ("ambientTemperation", "ambient_temperature", "Ambient Temperature", "°C", "temperature", "measurement"),
    ("RVolt", "grid_voltage", "Grid Voltage", "V", "voltage", "measurement"),
    ("RFreq", "grid_frequency", "Grid Frequency", "Hz", "frequency", "measurement"),
    ("pv1Volt", "pv1_voltage", "PV1 Voltage", "V", "voltage", "measurement"),
    ("pv2Volt", "pv2_voltage", "PV2 Voltage", "V", "voltage", "measurement"),
    ("currentFaultCount", "fault_count", "Fault Count", None, None, "measurement"),
]

logger = logging.getLogger("foxess_mqtt_bridge")


class FoxESSError(Exception):
    def __init__(self, errno: int, msg: str):
        super().__init__(f"errno={errno} {msg}")
        self.errno = errno


def signature(path: str, token: str, timestamp: str) -> str:
    # The Open API joins the three fields with the four literal characters
    # `\r\n` (backslash-r-backslash-n), not a CRLF — hence the raw string. A
    # real CRLF here yields errno 40256 "illegal signature".
    return hashlib.md5(fr"{path}\r\n{token}\r\n{timestamp}".encode()).hexdigest()


def parse_data_time(value: str | None) -> str | None:
    """The API reports e.g. '2026-09-18 16:01:10 BST+0100'; the zone
    abbreviation is decoration, the trailing numeric offset is authoritative."""
    if not value:
        return None
    match = re.fullmatch(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+\S*?([+-]\d{4})", value.strip())
    if not match:
        return None
    parsed = datetime.strptime(f"{match.group(1)}{match.group(2)}", "%Y-%m-%d %H:%M:%S%z")
    return parsed.strftime("%Y-%m-%dT%H:%M:%S%z")


def build_state(datas: list[dict], last_totals: dict[str, float]) -> dict:
    """Map the API's variable list onto the state payload.

    The cloud occasionally serves a lifetime counter as zero (or an older
    value) for a sample. Home Assistant reads any drop in a `total_increasing`
    sensor as a meter reset and re-adds the full counter on recovery, so a
    counter that goes backwards is held at its last good value instead.
    `last_totals` is updated in place."""
    by_variable = {d.get("variable"): d.get("value") for d in datas}
    state: dict = {}
    for variable, key, _name, _unit, _dev_class, state_class in SENSORS:
        value = by_variable.get(variable)
        if value is None or value == "":
            continue
        if state_class is not None and isinstance(value, str):
            # Some counters arrive as numeric strings ("0").
            try:
                value = float(value) if "." in value else int(value)
            except ValueError:
                continue
        if isinstance(value, float):
            # The API leaks binary float noise (0.10400000000000001).
            value = round(value, 3)
        if state_class == "total_increasing":
            if not isinstance(value, (int, float)):
                continue
            previous = last_totals.get(key)
            if previous is not None and value < previous:
                logger.warning("%s went backwards (%s -> %s); holding", key, previous, value)
                value = previous
            last_totals[key] = value
        state[key] = value
    return state


class FoxESSClient:
    def __init__(self, url: str, token: str, timeout: float):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "foxess-mqtt-bridge/1",
                "Content-Type": "application/json",
                "lang": "en",
            }
        )

    def _post(self, path: str, body: dict):
        timestamp = str(round(time.time() * 1000))
        headers = {
            "token": self.token,
            "timestamp": timestamp,
            "signature": signature(path, self.token, timestamp),
        }
        resp = self.session.post(
            f"{self.url}{path}", json=body, headers=headers, timeout=self.timeout
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("errno") != 0:
            raise FoxESSError(data.get("errno"), data.get("msg", ""))
        return data.get("result")

    def devices(self) -> list[dict]:
        result = self._post("/op/v0/device/list", {"currentPage": 1, "pageSize": 10})
        return (result or {}).get("data", [])

    def real_time(self, sn: str) -> dict:
        variables = [sensor[0] for sensor in SENSORS]
        result = self._post("/op/v0/device/real/query", {"sn": sn, "variables": variables})
        return result[0] if result else {}


class Bridge:
    def __init__(self, config: dict):
        api = config["api"]
        self.client = FoxESSClient(
            api.get("url", "https://www.foxesscloud.com"),
            Path(api["key_file"]).read_text().strip(),
            float(config.get("http_timeout", 30)),
        )
        self.device_sn: str | None = api.get("device_sn")
        self.device_model = "Inverter"
        self.poll_interval = int(config.get("poll_interval", 120))

        self.discovery_prefix = config.get("discovery", {}).get(
            "prefix", "homeassistant"
        )
        self.state_prefix = config.get("discovery", {}).get(
            "state_topic_prefix", "foxess"
        )

        self.mqtt = mqtt.Client(
            client_id=config["mqtt"].get("client_id", "foxess-mqtt-bridge")
        )
        self.mqtt.username_pw_set(
            config["mqtt"]["username"], self._read_password(config["mqtt"])
        )
        self.mqtt.will_set(self._availability_topic(), "offline", retain=True)
        self.mqtt.on_connect = self._on_mqtt_connect
        self.mqtt.on_disconnect = self._on_mqtt_disconnect

        self.mqtt_host = config["mqtt"]["host"]
        self.mqtt_port = int(config["mqtt"].get("port", 1883))

        self.last_totals: dict[str, float] = {}
        self._connected = False
        self._stop = threading.Event()

    @staticmethod
    def _read_password(mqtt_cfg: dict) -> str:
        if "password" in mqtt_cfg:
            return mqtt_cfg["password"]
        path = mqtt_cfg.get("password_file")
        if path:
            return Path(path).read_text().strip()
        raise SystemExit("config.mqtt: either password or password_file is required")

    def _availability_topic(self) -> str:
        return f"{self.state_prefix}/bridge/availability"

    def _state_topic(self) -> str:
        return f"{self.state_prefix}/{self.device_sn}/state"

    def _on_mqtt_connect(self, _client, _userdata, _flags, rc):
        if rc == 0:
            logger.info("mqtt connected")
            self._connected = True
            self.mqtt.publish(
                self._availability_topic(), "online", retain=True, qos=1
            )
            # Re-publish discovery on (re)connect in case retained messages
            # were wiped on the broker.
            self._publish_discovery()
        else:
            logger.warning("mqtt connect rc=%s", rc)

    def _on_mqtt_disconnect(self, _client, _userdata, rc):
        self._connected = False
        logger.warning("mqtt disconnected rc=%s", rc)

    def _publish_discovery(self) -> None:
        # The serial keys every topic and unique_id, so discovery has to wait
        # for it when it is being auto-resolved from the account.
        if not self._connected or self.device_sn is None:
            return

        device = {
            "identifiers": [f"foxess_{self.device_sn}"],
            "name": "FoxESS Inverter",
            "manufacturer": "FoxESS",
            "model": self.device_model,
        }
        sensors = [sensor[1:] for sensor in SENSORS]
        sensors.append(("last_update", "Last Update", None, "timestamp", None))

        for key, name, unit, dev_class, state_class in sensors:
            unique_id = f"foxess_{self.device_sn}_{key}"
            topic = f"{self.discovery_prefix}/sensor/{unique_id}/config"
            payload = {
                "name": name,
                "unique_id": unique_id,
                "state_topic": self._state_topic(),
                "value_template": (
                    f"{{{{ value_json.{key} | default(None) }}}}"
                ),
                "device": device,
                "availability_topic": self._availability_topic(),
            }
            if unit is not None:
                payload["unit_of_measurement"] = unit
            if dev_class is not None:
                payload["device_class"] = dev_class
            if state_class is not None:
                payload["state_class"] = state_class
            self.mqtt.publish(topic, json.dumps(payload), retain=True, qos=1)

        logger.info("discovery published for device …%s", self.device_sn[-4:])

    def _resolve_device(self) -> bool:
        """Fill in the serial (unless configured) and the model from the
        account's device list. Returns False if the device cannot be resolved
        yet."""
        try:
            devices = self.client.devices()
        except (requests.RequestException, ValueError, FoxESSError) as exc:
            logger.warning("device list failed: %s", exc)
            return self.device_sn is not None

        if self.device_sn is None:
            if not devices:
                logger.warning("no devices on the FoxESS account")
                return False
            if len(devices) > 1:
                logger.warning(
                    "%d devices on the account; using the first — set device_sn to choose",
                    len(devices),
                )
            self.device_sn = devices[0]["deviceSN"]

        for dev in devices:
            if dev.get("deviceSN") == self.device_sn:
                self.device_model = dev.get("deviceType") or self.device_model
        return True

    def _poll(self) -> int:
        """Poll once; returns the seconds to wait before the next poll."""
        try:
            result = self.client.real_time(self.device_sn)
        except FoxESSError as exc:
            if exc.errno == ERRNO_RATE_LIMITED:
                logger.warning("daily API quota exhausted; backing off %ss", RATE_LIMIT_BACKOFF)
                return max(self.poll_interval, RATE_LIMIT_BACKOFF)
            logger.warning("poll failed: %s", exc)
            return self.poll_interval
        except (requests.RequestException, ValueError) as exc:
            logger.warning("poll failed: %s", exc)
            return self.poll_interval

        state = build_state(result.get("datas", []), self.last_totals)
        state["last_update"] = parse_data_time(result.get("time"))
        self.mqtt.publish(self._state_topic(), json.dumps(state), retain=True, qos=0)
        logger.debug("published state (%d values)", len(state))
        return self.poll_interval

    def run(self) -> None:
        # connect_async + loop_start so MQTT availability is not a startup
        # precondition — the daemon stays up and reconnects when the broker
        # comes back.
        self.mqtt.connect_async(self.mqtt_host, self.mqtt_port, keepalive=60)
        self.mqtt.loop_start()

        try:
            while not self._stop.is_set() and not self._resolve_device():
                self._stop.wait(self.poll_interval)
            if not self._stop.is_set():
                logger.info(
                    "polling %s device …%s every %ss",
                    self.device_model,
                    self.device_sn[-4:],
                    self.poll_interval,
                )
                self._publish_discovery()
            while not self._stop.is_set():
                self._stop.wait(self._poll())
        finally:
            try:
                self.mqtt.publish(
                    self._availability_topic(), "offline", retain=True, qos=1
                ).wait_for_publish(timeout=2)
            except Exception:  # noqa: BLE001
                pass
            self.mqtt.loop_stop()
            self.mqtt.disconnect()

    def stop(self) -> None:
        self._stop.set()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("FOXESS_MQTT_BRIDGE_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    with CONFIG_PATH.open() as f:
        config = yaml.safe_load(f)
    bridge = Bridge(config)

    def _handle_signal(_signum, _frame):
        bridge.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    bridge.run()


if __name__ == "__main__":
    main()
