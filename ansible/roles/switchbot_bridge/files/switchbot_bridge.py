#!/usr/bin/env python3
"""switchbot_bridge — passive BLE listener that republishes SwitchBot Meter
readings to MQTT with Home Assistant discovery."""

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

import paho.mqtt.client as mqtt
import yaml
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

CONFIG_PATH = Path(
    os.environ.get("SWITCHBOT_BRIDGE_CONFIG", "/etc/switchbot-bridge/config.yml")
)

# SwitchBot uses two service UUIDs across firmware generations.
SWITCHBOT_SERVICE_UUIDS = (
    "0000_0d00_-0000-1000-8000-00805f9b34fb",  # legacy WoSensorTH
    "0000fd3d-0000-1000-8000-00805f9b34fb",  # newer firmware
)

# Device-type byte (first byte of the service-data payload).
METER_TYPES = (0x54, 0x69)  # 'T' = Meter, 'i' = Meter Plus

logger = logging.getLogger("switchbot_bridge")


def decode_meter(data: bytes):
    """Decode a WoSensorTH service-data payload.

    Returns {temperature, humidity, battery} or None when the payload does not
    look like a Meter (different SwitchBot device class, or truncated)."""
    if len(data) < 6 or data[0] not in METER_TYPES:
        return None
    battery = data[2] & 0x7F
    temp_frac = data[3] & 0x0F
    temp_int = data[4] & 0x7F
    temp_sign = 1 if (data[4] & 0x80) else -1
    humidity = data[5] & 0x7F
    return {
        "temperature": round(temp_sign * (temp_int + temp_frac / 10), 1),
        "humidity": humidity,
        "battery": battery,
    }


def slug_mac(mac: str) -> str:
    return mac.replace(":", "").lower()


def short_mac(mac: str) -> str:
    return slug_mac(mac)[-4:]


class Bridge:
    def __init__(self, config: dict):
        self.config = config
        self.discovery_prefix = config.get("discovery", {}).get("prefix", "homeassistant")
        self.state_prefix = config.get("discovery", {}).get(
            "state_topic_prefix", "switchbot"
        )
        self.adapter = config.get("scan", {}).get("adapter", "hci0")
        self.scanning_mode = config.get("scan", {}).get("mode", "active")
        self.devices_by_mac = {
            d["mac"].upper(): d for d in config.get("devices") or []
        }

        self.mqtt = mqtt.Client(
            client_id=config["mqtt"].get("client_id", "switchbot-bridge")
        )
        self.mqtt.username_pw_set(
            config["mqtt"]["username"], self._read_password()
        )
        self.mqtt.will_set(self._availability_topic(), "offline", retain=True)
        self.mqtt.on_connect = self._on_mqtt_connect
        self.mqtt.on_disconnect = self._on_mqtt_disconnect

        self.discovery_published: set[str] = set()
        self._stop_event: asyncio.Event | None = None

    def _read_password(self) -> str:
        mqtt_cfg = self.config["mqtt"]
        if "password" in mqtt_cfg:
            return mqtt_cfg["password"]
        path = mqtt_cfg.get("password_file")
        if path:
            return Path(path).read_text().strip()
        raise SystemExit("config.mqtt: either password or password_file is required")

    def _availability_topic(self) -> str:
        return f"{self.state_prefix}/bridge/availability"

    def _state_topic(self, mac: str) -> str:
        return f"{self.state_prefix}/{slug_mac(mac)}/state"

    def _friendly_name(self, mac: str) -> str:
        entry = self.devices_by_mac.get(mac)
        if entry and entry.get("friendly_name"):
            return entry["friendly_name"]
        return f"SwitchBot {short_mac(mac)}"

    def _on_mqtt_connect(self, _client, _userdata, _flags, rc):
        if rc == 0:
            logger.info("mqtt connected")
            self.mqtt.publish(self._availability_topic(), "online", retain=True, qos=1)
            # Force re-publish of discovery on reconnect, in case the broker
            # has been wiped of retained messages.
            self.discovery_published.clear()
        else:
            logger.warning("mqtt connect rc=%s", rc)

    def _on_mqtt_disconnect(self, _client, _userdata, rc):
        logger.warning("mqtt disconnected rc=%s", rc)

    def _publish_discovery(self, mac: str) -> None:
        if mac in self.discovery_published:
            return
        friendly = self._friendly_name(mac)
        device_block = {
            "identifiers": [f"switchbot_{slug_mac(mac)}"],
            "name": friendly,
            "manufacturer": "SwitchBot",
            "model": "WoSensorTH",
        }
        availability_topic = self._availability_topic()
        state_topic = self._state_topic(mac)

        sensors = (
            ("temperature", "Temperature", "°C", "temperature"),
            ("humidity", "Humidity", "%", "humidity"),
            ("battery", "Battery", "%", "battery"),
        )
        for key, name, unit, dev_class in sensors:
            unique_id = f"switchbot_{slug_mac(mac)}_{key}"
            topic = f"{self.discovery_prefix}/sensor/{unique_id}/config"
            payload = {
                "name": name,
                "unique_id": unique_id,
                "state_topic": state_topic,
                "value_template": f"{{{{ value_json.{key} }}}}",
                "unit_of_measurement": unit,
                "device_class": dev_class,
                "state_class": "measurement",
                "device": device_block,
                "availability_topic": availability_topic,
            }
            self.mqtt.publish(topic, json.dumps(payload), retain=True, qos=1)
        self.discovery_published.add(mac)
        logger.info("discovery published for %s (%s)", mac, friendly)

    def _on_advertisement(
        self, device: BLEDevice, adv: AdvertisementData
    ) -> None:
        payload = None
        for uuid in SWITCHBOT_SERVICE_UUIDS:
            if uuid in adv.service_data:
                payload = adv.service_data[uuid]
                break
        if payload is None:
            return
        decoded = decode_meter(payload)
        if not decoded:
            return
        mac = device.address.upper()
        self._publish_discovery(mac)
        self.mqtt.publish(
            self._state_topic(mac), json.dumps(decoded), retain=True, qos=0
        )
        logger.debug(
            "publish %s temp=%s humidity=%s battery=%s",
            mac,
            decoded["temperature"],
            decoded["humidity"],
            decoded["battery"],
        )

    async def run(self) -> None:
        self._stop_event = asyncio.Event()

        host = self.config["mqtt"]["host"]
        port = self.config["mqtt"].get("port", 1883)
        # connect_async + loop_start so MQTT availability is not a startup
        # precondition — the daemon stays up and reconnects when the broker
        # comes back.
        self.mqtt.connect_async(host, port, keepalive=60)
        self.mqtt.loop_start()

        async with BleakScanner(
            detection_callback=self._on_advertisement,
            scanning_mode=self.scanning_mode,
            adapter=self.adapter,
        ):
            logger.info(
                "scanner started on %s (%s mode)", self.adapter, self.scanning_mode
            )
            await self._stop_event.wait()

        # Tidy shutdown — best-effort.
        try:
            self.mqtt.publish(
                self._availability_topic(), "offline", retain=True, qos=1
            ).wait_for_publish(timeout=2)
        except Exception:  # noqa: BLE001
            pass
        self.mqtt.loop_stop()
        self.mqtt.disconnect()

    def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("SWITCHBOT_BRIDGE_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    with CONFIG_PATH.open() as f:
        config = yaml.safe_load(f)
    bridge = Bridge(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, bridge.stop)
    try:
        loop.run_until_complete(bridge.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
