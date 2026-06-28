#!/usr/bin/env python3
"""glow_energy_importer — pull settled half-hourly UK smart-meter data from the
Hildebrand/Glowmarkt DCC API and import it into Home Assistant as backdated
long-term statistics.

Why not a live MQTT sensor (the previous incarnation of this role)? The DCC feed
is delayed: a day's half-hourly readings only settle around 01:30 the following
morning. A live `total_increasing` sensor timestamps every reading at the moment
HA receives it, so delayed data lands on the wrong hour and "today" is forever
near-empty. Home Assistant's statistics layer, by contrast, accepts external
statistics at an explicit historical timestamp (the WebSocket
`recorder/import_statistics` command), which is the only mechanism that places each
reading on the half-hour it actually happened. The Energy dashboard reads those
statistics directly.

The importer is append-only and idempotent. It tracks a high-water mark per
statistic in the systemd StateDirectory; each run fetches the hours that have
settled since, accumulates a monotonic `sum`, and imports them. If the state file
is lost it re-imports the whole backfill window from scratch (recomputing every
sum from zero), so a wiped StateDirectory self-heals rather than leaving a sum
discontinuity that the Energy dashboard would render as a spike.

Cost is computed locally from a configured, date-effective time-of-use tariff
rather than read from the DCC, because the DCC cost/tariff feeds are empty for this
meter. When a tariff is configured the importer publishes a parallel cost statistic
alongside consumption, sharing one fetch but tracking its own high-water mark.
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import websocket
import yaml

CONFIG_PATH = Path(
    os.environ.get("GLOW_ENERGY_IMPORTER_CONFIG", "/etc/glow-energy-importer/config.yml")
)
STATE_DIR = Path(os.environ.get("STATE_DIRECTORY", "/var/lib/glow-energy-importer"))
TOKEN_CACHE = STATE_DIR / "token.json"
IMPORT_STATE = STATE_DIR / "import_state.json"

HOUR = 3600

# The DCC readings API caps a half-hourly (PT30M) query at ~10 days per request;
# stay comfortably under it when backfilling.
FETCH_CHUNK = timedelta(days=7)

# A local day D is "settled" once we are this far past the midnight that ends it.
# DCC data for D firms up by ~01:30 the next morning; 2h is a safe margin.
SETTLE_LAG = timedelta(hours=2)

logger = logging.getLogger("glow_energy_importer")


def hour_floor(ts: int) -> int:
    return ts - (ts % HOUR)


def _hm(value: str) -> int:
    """'HH:MM' local clock time -> minutes since local midnight."""
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


class Tariff:
    """Date-effective, time-of-use electricity tariff.

    A list of versions, each with an `effective_from` date, a `standing_charge`
    (GBP/day) and a set of `unit_rates` windows (GBP/kWh). The version in force on a
    given local date is the latest one whose `effective_from` is on or before it.
    Within that version a half-hour's rate is the window covering its local clock
    time: a window with neither `from` nor `to` is a flat all-day rate, and a window
    where `from` > `to` wraps past midnight (e.g. an overnight off-peak 23:00-06:00).
    A flat tariff is simply a single version with one window-less rate.
    """

    def __init__(self, versions: list[dict]):
        if not versions:
            raise ValueError("tariff has no versions")
        self.versions = sorted(versions, key=lambda v: v["effective_from"])

    def _version_for(self, local_date: date) -> dict:
        chosen = None
        for version in self.versions:
            if date.fromisoformat(version["effective_from"]) <= local_date:
                chosen = version
            else:
                break
        if chosen is None:
            raise ValueError(f"no tariff effective on {local_date}")
        return chosen

    def rate(self, local_dt: datetime) -> float:
        """Unit rate (GBP/kWh) in force at a local datetime."""
        version = self._version_for(local_dt.date())
        minute = local_dt.hour * 60 + local_dt.minute
        for window in version["unit_rates"]:
            if "from" not in window and "to" not in window:
                return float(window["rate"])
            start, end = _hm(window["from"]), _hm(window["to"])
            if start < end:
                if start <= minute < end:
                    return float(window["rate"])
            elif minute >= start or minute < end:  # window wraps past midnight
                return float(window["rate"])
        raise ValueError(f"no rate window covers {local_dt:%H:%M} on {local_dt.date()}")

    def standing_charge(self, local_date: date) -> float:
        """Daily standing charge (GBP/day) in force on a local date."""
        return float(self._version_for(local_date)["standing_charge"])


class GlowmarktClient:
    """Token auth (with caching) plus the read paths over the Glowmarkt DCC API."""

    def __init__(self, config: dict, session: requests.Session):
        glow = config["glow"]
        self.api = glow["url"].rstrip("/")
        self.application_id = glow["application_id"]
        self.username = glow["username"]
        self.password = self._read_secret(glow)
        self.http_timeout = float(config.get("http_timeout", 30))
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
            TOKEN_CACHE.write_text(json.dumps({"token": self._token, "exp": self._exp}))
        except OSError as exc:
            logger.warning("could not persist token cache: %s", exc)

    def _headers(self) -> dict:
        return {"applicationId": self.application_id, "token": self._token or ""}

    def _ensure_token(self) -> None:
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
            url, headers=self._headers(), params=params or None, timeout=self.http_timeout
        )
        # A token can be revoked server-side before its stated expiry; force a
        # single re-auth and retry once before giving up.
        if resp.status_code == 401:
            self._token = None
            self._ensure_token()
            resp = self.session.get(
                url, headers=self._headers(), params=params or None, timeout=self.http_timeout
            )
        resp.raise_for_status()
        return resp.json()

    def consumption_resource(self) -> str:
        """Resource ID of the electricity consumption resource."""
        for ve in self._get("virtualentity"):
            detail = self._get(f"virtualentity/{ve['veId']}/resources")
            for res in detail.get("resources", []):
                if res.get("classifier") == "electricity.consumption":
                    return res["resourceId"]
        raise SystemExit("no electricity.consumption resource found on account")

    def half_hourly(
        self, resource_id: str, frm: datetime, to: datetime
    ) -> list[tuple[int, float]]:
        """Native half-hourly readings as (epoch, kWh), chunked under the API's
        per-request range cap. Buckets with null values are dropped."""
        fmt = "%Y-%m-%dT%H:%M:%S"
        out: list[tuple[int, float]] = []
        cursor = frm
        while cursor < to:
            window_end = min(cursor + FETCH_CHUNK, to)
            data = self._get(
                f"resource/{resource_id}/readings",
                **{
                    "from": cursor.astimezone(timezone.utc).strftime(fmt),
                    "to": window_end.astimezone(timezone.utc).strftime(fmt),
                    "period": "PT30M",
                    "function": "sum",
                },
            )
            for ts, val in data.get("data") or []:
                if val is not None:
                    out.append((int(ts), float(val)))
            cursor = window_end
        return out


class HomeAssistantClient:
    """Imports external statistics via HA's WebSocket `recorder/import_statistics`
    command. There is no REST equivalent — `import_statistics` is not a registered
    service (only `purge`, `get_statistics`, etc. are), so it must go over the
    WebSocket API. The command upserts by (statistic_id, start), so re-importing an
    hour overwrites it rather than duplicating."""

    # Keep messages bounded on large backfills.
    BATCH = 1000

    def __init__(self, config: dict):
        ha = config["ha"]
        url = ha["url"].rstrip("/")
        self.ws_url = (
            url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
            + "/api/websocket"
        )
        self.token = self._read_token(ha)
        self.http_timeout = float(config.get("http_timeout", 30))

    @staticmethod
    def _read_token(ha_cfg: dict) -> str:
        if "token" in ha_cfg:
            return ha_cfg["token"]
        path = ha_cfg.get("token_file")
        if path:
            return Path(path).read_text().strip()
        raise SystemExit("config.ha: either token or token_file is required")

    def _connect(self):
        """Open an authenticated WebSocket. HA greets with auth_required, expects an
        auth message, then replies auth_ok before accepting commands."""
        ws = websocket.create_connection(self.ws_url, timeout=self.http_timeout)
        greeting = json.loads(ws.recv())
        if greeting.get("type") != "auth_required":
            ws.close()
            raise RuntimeError(f"unexpected HA greeting: {greeting.get('type')}")
        ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        ack = json.loads(ws.recv())
        if ack.get("type") != "auth_ok":
            ws.close()
            raise RuntimeError(f"HA auth failed: {ack.get('type')}")
        return ws

    def import_statistics(self, metadata: dict, stats: list[dict]) -> None:
        ws = self._connect()
        try:
            msg_id = 0
            for i in range(0, len(stats), self.BATCH):
                msg_id += 1
                ws.send(
                    json.dumps(
                        {
                            "id": msg_id,
                            "type": "recorder/import_statistics",
                            "metadata": metadata,
                            "stats": stats[i : i + self.BATCH],
                        }
                    )
                )
                reply = json.loads(ws.recv())
                if not reply.get("success"):
                    raise RuntimeError(f"import_statistics failed: {reply.get('error')}")
        finally:
            ws.close()


class Importer:
    def __init__(self, config: dict):
        self.poll_interval = int(config.get("poll_interval", 21600))
        self.backfill_days = int(config.get("backfill_days", 90))
        self.tz = ZoneInfo(config.get("timezone", "Europe/London"))

        stats = config.get("statistics", {})
        self.consumption_id = stats.get("consumption_id", "glow:electricity_consumption")
        self.consumption_name = stats.get("consumption_name", "Electricity consumption")
        self.cost_id = stats.get("cost_id", "glow:electricity_cost")
        self.cost_name = stats.get("cost_name", "Electricity cost")
        self.currency = config.get("currency", "GBP")
        tariffs = config.get("tariffs") or []
        self.tariff = Tariff(tariffs) if tariffs else None

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "glow-energy-importer/1"})
        self.glow = GlowmarktClient(config, self.session)
        self.ha = HomeAssistantClient(config)
        self.resource_id: str | None = None

        self._stop = threading.Event()

    # --- high-water-mark state -------------------------------------------------

    def _load_state(self) -> dict:
        try:
            return json.loads(IMPORT_STATE.read_text())
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: dict) -> None:
        IMPORT_STATE.write_text(json.dumps(state))

    def _settle_cutoff(self) -> datetime:
        """First instant that is *not* yet importable: the local midnight ending
        the most recent fully-settled day. Half-hours at or after this are
        skipped."""
        now_local = datetime.now(self.tz)
        latest_settled_day = (now_local - SETTLE_LAG).date() - timedelta(days=1)
        end_of_day_local = datetime.combine(
            latest_settled_day + timedelta(days=1),
            datetime.min.time(),
            tzinfo=self.tz,
        )
        return end_of_day_local.astimezone(timezone.utc)

    # --- the import itself -----------------------------------------------------

    def _local(self, ts: int) -> datetime:
        return datetime.fromtimestamp(ts, timezone.utc).astimezone(self.tz)

    def _series_plan(self, statistic_id: str) -> dict:
        """Decide the import window and starting cumulative sum for one statistic
        from its own high-water mark. Kept per-statistic so a newly-added series
        (e.g. cost) can backfill its full history while consumption only appends."""
        state = self._load_state().get(statistic_id)
        if state:
            # Append-only: continue the running sum from the last imported hour.
            # Over-fetch slightly to absorb boundary slack; the hour filter in
            # `_bucket` discards anything already imported.
            last_hour = int(state["last_hour"])
            frm = datetime.fromtimestamp(last_hour, timezone.utc) - timedelta(hours=2)
            return {"frm": frm, "first_excl": last_hour, "running": float(state["last_sum"])}
        # No state: rebuild the whole window from zero so every sum is internally
        # consistent and overwrites any stale import.
        frm = (datetime.now(timezone.utc) - timedelta(days=self.backfill_days)).replace(
            minute=0, second=0, microsecond=0
        )
        logger.info("no state for %s; backfilling %s days", statistic_id, self.backfill_days)
        return {"frm": frm, "first_excl": -1, "running": 0.0}

    @staticmethod
    def _bucket(rows, first_excl: int, cutoff_ts: int, value) -> dict[int, float]:
        """Aggregate native half-hours into UTC hour buckets via `value(ts, kwh)`,
        keeping only settled, not-yet-imported hours."""
        hourly: dict[int, float] = {}
        for ts, kwh in rows:
            h = hour_floor(ts)
            if h <= first_excl or h >= cutoff_ts:
                continue
            hourly[h] = hourly.get(h, 0.0) + value(ts, kwh)
        return hourly

    def _finalise(self, statistic_id, name, unit, hourly, running, places) -> None:
        if not hourly:
            logger.info("no new settled hours for %s", statistic_id)
            return
        stats = []
        cumulative = running
        for h in sorted(hourly):
            cumulative += hourly[h]
            value = round(cumulative, places)
            start = datetime.fromtimestamp(h, timezone.utc).isoformat()
            stats.append({"start": start, "state": value, "sum": value})

        metadata = {
            "has_mean": False,
            "has_sum": True,
            "source": statistic_id.split(":", 1)[0],
            "statistic_id": statistic_id,
            "name": name,
            "unit_of_measurement": unit,
        }
        self.ha.import_statistics(metadata, stats)

        new_last_hour = max(hourly)
        full_state = self._load_state()
        full_state[statistic_id] = {"last_hour": new_last_hour, "last_sum": round(cumulative, places)}
        self._save_state(full_state)
        logger.info(
            "imported %d hour(s) into %s up to %s (cumulative %.4g %s)",
            len(stats),
            statistic_id,
            datetime.fromtimestamp(new_last_hour, timezone.utc).isoformat(),
            cumulative,
            unit,
        )

    def _run_import(self) -> None:
        cutoff = self._settle_cutoff()
        cutoff_ts = int(cutoff.timestamp())

        plans = {self.consumption_id: self._series_plan(self.consumption_id)}
        if self.tariff:
            plans[self.cost_id] = self._series_plan(self.cost_id)

        # One fetch covers both series; each filters to its own window in `_bucket`.
        union_frm = min(p["frm"] for p in plans.values())
        if union_frm >= cutoff:
            logger.info("nothing new settled since last import (cutoff=%s)", cutoff.isoformat())
            return
        rows = self.glow.half_hourly(self.resource_id, union_frm, cutoff)

        cons = plans[self.consumption_id]
        self._finalise(
            self.consumption_id,
            self.consumption_name,
            "kWh",
            self._bucket(rows, cons["first_excl"], cutoff_ts, lambda ts, kwh: kwh),
            cons["running"],
            3,
        )

        if self.tariff:
            cp = plans[self.cost_id]
            cost_hourly = self._bucket(
                rows,
                cp["first_excl"],
                cutoff_ts,
                lambda ts, kwh: kwh * self.tariff.rate(self._local(ts)),
            )
            # The standing charge accrues per day regardless of use; spread it
            # evenly across each settled day's 24 hours.
            for h in cost_hourly:
                cost_hourly[h] += self.tariff.standing_charge(self._local(h).date()) / 24.0
            self._finalise(self.cost_id, self.cost_name, self.currency, cost_hourly, cp["running"], 4)

    def _poll(self) -> None:
        try:
            self._run_import()
        except (
            requests.RequestException,
            websocket.WebSocketException,
            OSError,
            ValueError,
            RuntimeError,
        ) as exc:
            logger.warning("import failed: %s", exc)

    def run(self) -> None:
        self.resource_id = self.glow.consumption_resource()
        targets = [self.consumption_id] + ([self.cost_id] if self.tariff else [])
        logger.info(
            "importing resource=%s into %s every %ss",
            self.resource_id,
            ", ".join(targets),
            self.poll_interval,
        )
        while not self._stop.is_set():
            self._poll()
            self._stop.wait(self.poll_interval)

    def stop(self) -> None:
        self._stop.set()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("GLOW_ENERGY_IMPORTER_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    with CONFIG_PATH.open() as f:
        config = yaml.safe_load(f)
    importer = Importer(config)

    def _handle_signal(_signum, _frame):
        importer.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    importer.run()


if __name__ == "__main__":
    main()
