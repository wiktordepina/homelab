#!/usr/bin/env python3
"""signum_mqtt_bridge — periodic poller that republishes Signum pool and
account metrics to MQTT with Home Assistant discovery.

Two sources are polled independently each tick:
  * the Signum pool's miner endpoint (e.g. pool.signumcoin.ro/api/getMiner/<id>)
  * the standard Signum node `getAccount` endpoint

A failure in one source does not stop the other from publishing — each pair of
state topics carries its own `last_update` timestamp so a frozen value is
visible at a glance in Home Assistant.
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import requests
import yaml

CONFIG_PATH = Path(
    os.environ.get("SIGNUM_MQTT_BRIDGE_CONFIG", "/etc/signum-mqtt-bridge/config.yml")
)

NQT_PER_SIGNA = 100_000_000

logger = logging.getLogger("signum_mqtt_bridge")


def signa_from_nqt(value: str | int | None) -> float | None:
    if value is None:
        return None
    try:
        return round(int(value) / NQT_PER_SIGNA, 8)
    except (TypeError, ValueError):
        return None


def signa_from_pool_string(value: str | None) -> float | None:
    """Pool strings look like '5.225 SIGNA' or '96721 SIGNA'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    head = str(value).split(" ", 1)[0].replace(",", "")
    try:
        return float(head)
    except ValueError:
        return None


def first_if_list(value):
    """Pool boost is sometimes an array of recent samples and sometimes a
    scalar. The first element is the most recent reading, so use it when an
    array is returned."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


class Bridge:
    def __init__(self, config: dict):
        self.account_id = str(config["account"]["id"])
        self.pool_url = config["pool"]["url"].rstrip("/")
        self.node_url = config["node"]["url"].rstrip("/")
        self.poll_interval = int(config.get("poll_interval", 60))
        self.http_timeout = float(config.get("http_timeout", 10))

        self.discovery_prefix = config.get("discovery", {}).get(
            "prefix", "homeassistant"
        )
        self.state_prefix = config.get("discovery", {}).get(
            "state_topic_prefix", "signum"
        )

        self.mqtt = mqtt.Client(
            client_id=config["mqtt"].get(
                "client_id", f"signum-mqtt-bridge-{self.account_id}"
            )
        )
        self.mqtt.username_pw_set(
            config["mqtt"]["username"], self._read_password(config["mqtt"])
        )
        self.mqtt.will_set(self._availability_topic(), "offline", retain=True)
        self.mqtt.on_connect = self._on_mqtt_connect
        self.mqtt.on_disconnect = self._on_mqtt_disconnect

        self.mqtt_host = config["mqtt"]["host"]
        self.mqtt_port = int(config["mqtt"].get("port", 1883))

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "signum-mqtt-bridge/1"})

        self.discovery_published = False
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

    def _pool_state_topic(self) -> str:
        return f"{self.state_prefix}/{self.account_id}/pool"

    def _account_state_topic(self) -> str:
        return f"{self.state_prefix}/{self.account_id}/account"

    def _on_mqtt_connect(self, _client, _userdata, _flags, rc):
        if rc == 0:
            logger.info("mqtt connected")
            self.mqtt.publish(
                self._availability_topic(), "online", retain=True, qos=1
            )
            # Re-publish discovery on (re)connect in case retained messages
            # were wiped on the broker.
            self.discovery_published = False
            self._publish_discovery()
        else:
            logger.warning("mqtt connect rc=%s", rc)

    def _on_mqtt_disconnect(self, _client, _userdata, rc):
        logger.warning("mqtt disconnected rc=%s", rc)

    def _device_block(self) -> dict:
        return {
            "identifiers": [f"signum_{self.account_id}"],
            "name": f"Signum {self.account_id}",
            "manufacturer": "Signum Network",
            "model": "Account / Pool Miner",
        }

    def _publish_discovery(self) -> None:
        if self.discovery_published:
            return

        device = self._device_block()
        availability_topic = self._availability_topic()
        pool_topic = self._pool_state_topic()
        account_topic = self._account_state_topic()

        # (key, name, unit, device_class, state_class, state_topic)
        sensors = [
            # Pool — capacity / commitment
            ("total_capacity", "Total Capacity", "TiB", None, "measurement", pool_topic),
            ("effective_capacity", "Effective Capacity", "TiB", None, "measurement", pool_topic),
            ("commitment_per_tib", "Commitment per TiB", "SIGNA", "monetary", None, pool_topic),
            ("committed_balance", "Committed Balance", "SIGNA", "monetary", None, pool_topic),
            ("boost", "Boost", None, None, "measurement", pool_topic),
            # Pool — earnings / share
            ("pending_balance", "Pending Balance", "SIGNA", "monetary", None, pool_topic),
            ("share_percent", "Pool Share", "%", None, "measurement", pool_topic),
            ("shared_capacity_percent", "Shared Capacity", "%", None, "measurement", pool_topic),
            ("confirmed_deadlines", "Confirmed Deadlines", None, None, "measurement", pool_topic),
            ("current_round_best_deadline", "Current Round Best Deadline", "s", "duration", "measurement", pool_topic),
            # Pool — diagnostics
            ("miner_user_agent", "Miner User Agent", None, None, None, pool_topic),
            ("pool_last_update", "Pool Last Update", None, "timestamp", None, pool_topic),
            # Account
            ("total_balance", "Total Balance", "SIGNA", "monetary", None, account_topic),
            ("available_balance", "Available Balance", "SIGNA", "monetary", None, account_topic),
            ("guaranteed_balance", "Guaranteed Balance", "SIGNA", "monetary", None, account_topic),
            ("forged_balance", "Forged Balance", "SIGNA", "monetary", None, account_topic),
            ("account_last_update", "Account Last Update", None, "timestamp", None, account_topic),
        ]

        for key, name, unit, dev_class, state_class, state_topic in sensors:
            unique_id = f"signum_{self.account_id}_{key}"
            topic = f"{self.discovery_prefix}/sensor/{unique_id}/config"
            payload = {
                "name": name,
                "unique_id": unique_id,
                "state_topic": state_topic,
                "value_template": (
                    f"{{{{ value_json.{key} | default(None) }}}}"
                ),
                "device": device,
                "availability_topic": availability_topic,
            }
            if unit is not None:
                payload["unit_of_measurement"] = unit
            if dev_class is not None:
                payload["device_class"] = dev_class
            if state_class is not None:
                payload["state_class"] = state_class
            self.mqtt.publish(topic, json.dumps(payload), retain=True, qos=1)

        self.discovery_published = True
        logger.info("discovery published for account %s", self.account_id)

    def _poll_pool(self) -> None:
        url = f"{self.pool_url}/api/getMiner/{self.account_id}"
        try:
            resp = self.session.get(url, timeout=self.http_timeout)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("pool poll failed: %s", exc)
            return

        boost_value = first_if_list(data.get("boost"))
        share_fraction = data.get("share")
        shared_capacity_percent = None
        if isinstance(share_fraction, (int, float)):
            shared_capacity_percent = round(share_fraction * 100, 4)

        deadline_raw = data.get("currentRoundBestDeadline")
        try:
            deadline = int(deadline_raw) if deadline_raw is not None else None
        except (TypeError, ValueError):
            deadline = None

        state = {
            "pending_balance": signa_from_pool_string(data.get("pendingBalance")),
            "committed_balance": signa_from_pool_string(data.get("committedBalance")),
            "commitment_per_tib": signa_from_pool_string(data.get("commitment")),
            "total_capacity": data.get("totalCapacity"),
            "effective_capacity": data.get("totalEffectiveCapacity"),
            "boost": (
                round(float(boost_value), 6)
                if isinstance(boost_value, (int, float))
                else None
            ),
            "share_percent": data.get("sharePercent"),
            "shared_capacity_percent": shared_capacity_percent,
            "confirmed_deadlines": data.get("nConf"),
            "current_round_best_deadline": deadline,
            "miner_user_agent": data.get("userAgent"),
            "pool_last_update": iso_now(),
        }

        self.mqtt.publish(
            self._pool_state_topic(), json.dumps(state), retain=True, qos=0
        )
        logger.debug("published pool state for %s", self.account_id)

    def _poll_account(self) -> None:
        url = f"{self.node_url}/api"
        params = {"requestType": "getAccount", "account": self.account_id}
        try:
            resp = self.session.get(url, params=params, timeout=self.http_timeout)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("account poll failed: %s", exc)
            return

        if "errorCode" in data:
            logger.warning("account poll error: %s", data)
            return

        state = {
            "total_balance": signa_from_nqt(data.get("balanceNQT")),
            "available_balance": signa_from_nqt(data.get("unconfirmedBalanceNQT")),
            "guaranteed_balance": signa_from_nqt(data.get("guaranteedBalanceNQT")),
            "forged_balance": signa_from_nqt(data.get("forgedBalanceNQT")),
            "account_last_update": iso_now(),
        }

        self.mqtt.publish(
            self._account_state_topic(), json.dumps(state), retain=True, qos=0
        )
        logger.debug("published account state for %s", self.account_id)

    def run(self) -> None:
        # connect_async + loop_start so MQTT availability is not a startup
        # precondition — the daemon stays up and reconnects when the broker
        # comes back.
        self.mqtt.connect_async(self.mqtt_host, self.mqtt_port, keepalive=60)
        self.mqtt.loop_start()

        logger.info(
            "polling pool=%s node=%s account=%s every %ss",
            self.pool_url,
            self.node_url,
            self.account_id,
            self.poll_interval,
        )

        try:
            while not self._stop.is_set():
                self._poll_pool()
                self._poll_account()
                self._stop.wait(self.poll_interval)
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
        level=os.environ.get("SIGNUM_MQTT_BRIDGE_LOG_LEVEL", "INFO"),
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
