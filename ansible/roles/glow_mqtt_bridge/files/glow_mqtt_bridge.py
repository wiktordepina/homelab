#!/usr/bin/env python3
"""glow_mqtt_bridge — periodic poller that republishes UK smart-meter
consumption, cost and tariff data (via the Hildebrand/Glowmarkt DCC API) to
MQTT with Home Assistant discovery.

Unlike the signum bridge, the Glowmarkt API is authenticated and the meter's
resources are not known ahead of time: each fuel's consumption/cost resource
IDs are discovered after login and cached for the life of the process. The auth
token is long-lived (~18 months on the accounts seen) and is persisted to the
systemd StateDirectory so a restart does not re-authenticate every boot.

DCC data is half-hourly and delayed; the daemon polls slowly (default 30 min)
and publishes today's running total per fuel plus the current tariff. A failure
polling one fuel does not stop the others — each fuel's state topic carries its
own `last_update`, so a frozen value is visible at a glance in Home Assistant.
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
    os.environ.get("GLOW_MQTT_BRIDGE_CONFIG", "/etc/glow-mqtt-bridge/config.yml")
)
# systemd sets STATE_DIRECTORY when the unit declares StateDirectory=; fall back
# to the conventional path for ad-hoc runs.
STATE_DIR = Path(os.environ.get("STATE_DIRECTORY", "/var/lib/glow-mqtt-bridge"))
TOKEN_CACHE = STATE_DIR / "token.json"

# Fuels we know how to map, keyed by the Glowmarkt resource `classifier`.
# Electricity-only accounts simply yield no gas resources.
FUELS = ("electricity", "gas")

logger = logging.getLogger("glow_mqtt_bridge")


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


def pence_to_gbp(value) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 100.0, 4)
    except (TypeError, ValueError):
        return None


class GlowmarktClient:
    """Thin wrapper over the Glowmarkt/Bright API: token auth with caching plus
    the read paths (resource discovery, readings, tariff)."""

    def __init__(self, config: dict, session: requests.Session):
        glow = config["glow"]
        self.api = glow["url"].rstrip("/")
        self.application_id = glow["application_id"]
        self.username = glow["username"]
        self.password = self._read_secret(glow)
        self.http_timeout = float(config.get("http_timeout", 15))
        self.session = session
        self._token: str | None = None
        self._exp: float = 0.0
        self._load_cached_token()

    @staticmethod
    def _read_secret(glow_cfg: dict) -> str:
        if "password" in glow_cfg:
            return glow_cfg["password"]
        path = glow_cfg.get("password_file")
        if path:
            return Path(path).read_text().strip()
        raise SystemExit("config.glow: either password or password_file is required")

    def _load_cached_token(self) -> None:
        try:
            cached = json.loads(TOKEN_CACHE.read_text())
            self._token = cached["token"]
            self._exp = float(cached["exp"])
            logger.info("loaded cached token (exp=%s)", int(self._exp))
        except (OSError, ValueError, KeyError):
            pass

    def _save_cached_token(self) -> None:
        try:
            TOKEN_CACHE.write_text(
                json.dumps({"token": self._token, "exp": self._exp})
            )
        except OSError as exc:
            logger.warning("could not persist token cache: %s", exc)

    def _headers(self) -> dict:
        return {"applicationId": self.application_id, "token": self._token or ""}

    def _ensure_token(self) -> None:
        # Refresh when missing or within five minutes of expiry.
        if self._token and time.time() < self._exp - 300:
            return
        logger.info("authenticating with Glowmarkt")
        resp = self.session.post(
            f"{self.api}/auth",
            json={"username": self.username, "password": self.password},
            headers={"applicationId": self.application_id},
            timeout=self.http_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("valid", False):
            raise RuntimeError(f"auth rejected: valid={data.get('valid')}")
        self._token = data["token"]
        self._exp = float(data["exp"])
        self._save_cached_token()

    def _get(self, path: str, **params):
        self._ensure_token()
        url = f"{self.api}/{path}"
        resp = self.session.get(
            url, headers=self._headers(), params=params or None,
            timeout=self.http_timeout,
        )
        # A token can be revoked server-side before its stated expiry; force a
        # single re-auth and retry once before giving up.
        if resp.status_code == 401:
            self._token = None
            self._ensure_token()
            resp = self.session.get(
                url, headers=self._headers(), params=params or None,
                timeout=self.http_timeout,
            )
        resp.raise_for_status()
        return resp.json()

    def discover_resources(self) -> dict:
        """Return {fuel: {"consumption": rid, "cost": rid}} for fuels present."""
        out: dict[str, dict] = {}
        for ve in self._get("virtualentity"):
            detail = self._get(f"virtualentity/{ve['veId']}/resources")
            for res in detail.get("resources", []):
                classifier = res.get("classifier", "")
                for fuel in FUELS:
                    if classifier == f"{fuel}.consumption":
                        out.setdefault(fuel, {})["consumption"] = res["resourceId"]
                    elif classifier == f"{fuel}.consumption.cost":
                        out.setdefault(fuel, {})["cost"] = res["resourceId"]
        logger.info("discovered fuels: %s", {f: list(r) for f, r in out.items()})
        return out

    def today_total(self, resource_id: str):
        """Sum of today's readings for a resource (kWh for consumption, pence
        for cost). Returns None when DCC has no data for today yet."""
        now = datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        fmt = "%Y-%m-%dT%H:%M:%S"
        data = self._get(
            f"resource/{resource_id}/readings",
            **{
                "from": midnight.strftime(fmt),
                "to": now.strftime(fmt),
                "period": "P1D",
                "function": "sum",
            },
        )
        rows = data.get("data") or []
        if rows and rows[0][1] is not None:
            return rows[0][1]
        return None

    def tariff(self, resource_id: str) -> dict:
        """Current standing charge and unit rate in GBP. Returns Nones when the
        DCC tariff feed has not populated (common on freshly-validated meters)."""
        data = self._get(f"resource/{resource_id}/tariff")
        rows = data.get("data") or []
        rates = (rows[0].get("currentRates") if rows else None) or {}
        return {
            "standing_charge": pence_to_gbp(rates.get("standingCharge")),
            "rate": pence_to_gbp(rates.get("rate")),
        }


class Bridge:
    def __init__(self, config: dict):
        self.poll_interval = int(config.get("poll_interval", 1800))

        self.discovery_prefix = config.get("discovery", {}).get(
            "prefix", "homeassistant"
        )
        self.state_prefix = config.get("discovery", {}).get(
            "state_topic_prefix", "glow"
        )

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "glow-mqtt-bridge/1"})
        self.client = GlowmarktClient(config, self.session)
        self.resources: dict[str, dict] = {}

        self.mqtt = mqtt.Client(
            client_id=config["mqtt"].get("client_id", "glow-mqtt-bridge")
        )
        self.mqtt.username_pw_set(
            config["mqtt"]["username"], self._read_password(config["mqtt"])
        )
        self.mqtt.will_set(self._availability_topic(), "offline", retain=True)
        self.mqtt.on_connect = self._on_mqtt_connect
        self.mqtt.on_disconnect = self._on_mqtt_disconnect

        self.mqtt_host = config["mqtt"]["host"]
        self.mqtt_port = int(config["mqtt"].get("port", 1883))

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

    def _state_topic(self, fuel: str) -> str:
        return f"{self.state_prefix}/{fuel}/state"

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

    def _device_block(self, fuel: str) -> dict:
        return {
            "identifiers": [f"glow_{fuel}"],
            "name": f"Smart Meter {fuel.title()}",
            "manufacturer": "Hildebrand Glowmarkt (DCC)",
            "model": "UK SMETS",
        }

    def _publish_discovery(self) -> None:
        if self.discovery_published:
            return

        availability_topic = self._availability_topic()

        # (key, name, unit, device_class, state_class)
        sensors = [
            ("usage_today", "Usage Today", "kWh", "energy", "total_increasing"),
            ("cost_today", "Cost Today", "GBP", "monetary", "total_increasing"),
            ("standing_charge", "Standing Charge", "GBP", "monetary", "measurement"),
            ("rate", "Rate", "GBP/kWh", None, "measurement"),
            ("last_update", "Last Update", None, "timestamp", None),
        ]

        for fuel in self.resources:
            device = self._device_block(fuel)
            state_topic = self._state_topic(fuel)
            for key, name, unit, dev_class, state_class in sensors:
                unique_id = f"glow_{fuel}_{key}"
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
        logger.info("discovery published for fuels %s", list(self.resources))

    def _poll_fuel(self, fuel: str, rids: dict) -> None:
        try:
            usage = self.client.today_total(rids["consumption"])
            cost = (
                pence_to_gbp(self.client.today_total(rids["cost"]))
                if "cost" in rids
                else None
            )
            tar = self.client.tariff(rids["consumption"])
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            logger.warning("%s poll failed: %s", fuel, exc)
            return

        state = {
            "usage_today": round(usage, 4) if usage is not None else None,
            "cost_today": cost,
            "standing_charge": tar["standing_charge"],
            "rate": tar["rate"],
            "last_update": iso_now(),
        }
        self.mqtt.publish(
            self._state_topic(fuel), json.dumps(state), retain=True, qos=0
        )
        logger.debug("published %s state", fuel)

    def run(self) -> None:
        # Resource discovery is a precondition for discovery publication (the
        # sensor set depends on which fuels exist). A failure here exits the
        # process; systemd's RestartSec throttles the retry until the API is
        # reachable again.
        self.resources = self.client.discover_resources()
        if not self.resources:
            raise SystemExit("no fuels discovered; check account has DCC data")

        # connect_async + loop_start so MQTT availability is not a startup
        # precondition — the daemon stays up and reconnects when the broker
        # comes back.
        self.mqtt.connect_async(self.mqtt_host, self.mqtt_port, keepalive=60)
        self.mqtt.loop_start()

        logger.info(
            "polling api=%s fuels=%s every %ss",
            self.client.api,
            list(self.resources),
            self.poll_interval,
        )

        try:
            while not self._stop.is_set():
                for fuel, rids in self.resources.items():
                    self._poll_fuel(fuel, rids)
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
        level=os.environ.get("GLOW_MQTT_BRIDGE_LOG_LEVEL", "INFO"),
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
