# foxess_mqtt_bridge

FoxESS Cloud (solar inverter + battery) to MQTT bridge.

## Description

Installs a small Python daemon that periodically polls the FoxESS Cloud **Open API** for an inverter's real-time data — PV, load, grid and battery power, the lifetime energy counters, battery state of charge, temperatures — and republishes it to MQTT in Home Assistant discovery format. The inverter appears in HA as a single device.

The smart-meter feed (see the `glow_energy_importer` role) only ever sees the net flow at the grid boundary. Everything behind the meter — generation, battery charge and discharge, true house load — is only known to the inverter, which is what this bridge exposes.

The daemon only observes; it never writes settings to the inverter.

### Freshness

The inverter's datalogger uploads to the cloud on its own schedule (about every five minutes), so the cloud is the bottleneck, not the poll interval. Each state payload carries the cloud's own data timestamp as `Last Update`; that, not the time of the poll, is how old the readings are. This feed suits the Energy dashboard and trend charts. A genuinely live display needs a local source (Modbus over RS485) instead.

### API quota

The Open API allows 1,440 calls per day per key. One `device/real/query` call returns every variable, so each poll costs one call; the default 120 s interval uses half the quota and still samples each cloud update at least twice. If the quota is exhausted the API answers `errno 40400` and the daemon backs off for 15 minutes at a time until it resets.

## Tasks

- Installs `python3-venv` and `python3-packaging`.
- Creates a system user `foxess-mqtt-bridge`.
- Builds a Python virtual environment under `/opt/foxess-mqtt-bridge/venv`.
- Installs `paho-mqtt`, `requests`, and `PyYAML` from the pinned `requirements.txt`.
- Drops the daemon at `/opt/foxess-mqtt-bridge/foxess_mqtt_bridge.py`.
- Templates `/etc/foxess-mqtt-bridge/config.yml` with the API endpoint, poll interval, and MQTT broker details.
- Drops two plaintext secret files (mode `0640`, group-readable by `foxess-mqtt-bridge`): the FoxESS API key and the MQTT password.
- Installs and enables a systemd unit with the standard hardening directives.

## Requirements

- Debian-based OS with outbound HTTPS to `www.foxesscloud.com`.
- A **FoxESS Cloud API key**: log in to <https://www.foxesscloud.com>, open the profile menu → *User Profile* → *API Management* → *Generate API Key*. Generating a new key invalidates the previous one.
- An MQTT broker reachable from the host (this homelab's `mosquitto` LXC).
- A broker user dedicated to the bridge (see *MQTT credential* below).

## Variables

| Name | Required | Default | Description |
|---|---|---|---|
| `foxess_mqtt_bridge_api_key_env` | yes | — | Name of the env var on the runner that holds the FoxESS Cloud API key. |
| `foxess_mqtt_bridge_device_sn` | no | first device on the account | Inverter serial number. Leave unset on a single-inverter account: the daemon resolves it from the API at start-up, which keeps the serial out of the repository. |
| `foxess_mqtt_bridge_api_url` | no | `https://www.foxesscloud.com` | Base URL of the FoxESS Cloud. |
| `foxess_mqtt_bridge_poll_interval` | no | `120` | Seconds between polls. See *API quota* before lowering it; below 60 the daily quota cannot last the day. |
| `foxess_mqtt_bridge_http_timeout` | no | `30` | Per-request timeout in seconds. |
| `foxess_mqtt_bridge_mqtt_host` | yes | — | Broker hostname or IP. |
| `foxess_mqtt_bridge_mqtt_port` | no | `1883` | Broker port. |
| `foxess_mqtt_bridge_mqtt_username` | yes | — | Username on the broker. |
| `foxess_mqtt_bridge_mqtt_password_env` | yes | — | Name of the env var on the runner that holds the **plaintext** password (the broker stores the corresponding hash; see the `mosquitto` role README). |
| `foxess_mqtt_bridge_mqtt_client_id` | no | `<hostname>-foxess-mqtt-bridge` | MQTT client ID. |
| `foxess_mqtt_bridge_discovery_prefix` | no | `homeassistant` | HA's MQTT discovery prefix. |
| `foxess_mqtt_bridge_state_topic_prefix` | no | `foxess` | Top-level prefix for state and availability topics. |

## Dependencies

- `base` (apt update/upgrade).

## Example usage

```yaml
ansible:
  roles:
    - base
    - role: foxess_mqtt_bridge
      vars:
        foxess_mqtt_bridge_api_key_env: FOXESS_API_KEY
        foxess_mqtt_bridge_mqtt_host: mosquitto.home.matagoth.com
        foxess_mqtt_bridge_mqtt_username: foxess-bridge
        foxess_mqtt_bridge_mqtt_password_env: MOSQUITTO_PASSWORD_FOXESS_BRIDGE
```

## How the inverter appears in Home Assistant

All sensors auto-discover under a single HA device named `FoxESS Inverter` (its model is read from the API), from one JSON state topic `foxess/<serial>/state`.

**Power (kW)**

- `PV Power`, plus `PV1 Power` / `PV2 Power` per string
- `Load Power` — true house consumption
- `Grid Import Power` / `Grid Export Power` — each non-negative
- `Grid Power` — signed, positive = importing
- `Battery Charge Power` / `Battery Discharge Power` — each non-negative
- `Battery Power` — signed, positive = discharging
- `Inverter Output Power`, `EPS Power`

The split series suit the Energy dashboard and most cards; the two signed series are for power-flow cards that want a single entity per node.

**Energy (kWh, lifetime counters, `total_increasing`)**

- `PV Energy`, `Load Energy`, `Inverter Output Energy`
- `Grid Import Energy` / `Grid Export Energy`
- `Battery Charge Energy` / `Battery Discharge Energy`

**Battery** — `Battery SoC`, `Battery SoH`, `Battery Temperature`, `Battery Voltage`, `Battery Cycle Count`, `Battery Status` (text, e.g. `Charge` / `Discharge`).

**Inverter / grid** — `Inverter Temperature`, `Ambient Temperature`, `Grid Voltage`, `Grid Frequency`, `PV1 Voltage` / `PV2 Voltage`, `Fault Count`, `Last Update` (timestamp of the cloud's data, see *Freshness*).

The bridge also publishes its own availability under `foxess/bridge/availability` (`online` / `offline`); each sensor's discovery payload references this topic so HA marks all readings unavailable if the bridge dies. A frozen `Last Update` while the bridge is online means the inverter has stopped uploading (or the cloud is down), not that the bridge is broken.

## Credentials

The API key is sourced from the runner env var named by `foxess_mqtt_bridge_api_key_env`, added alongside the other runner secrets (e.g. `/pve/secrets/energy.sh`):

```bash
export FOXESS_API_KEY='<api-key>'
```

### MQTT credential

A dedicated broker user keeps the bridge's blast radius small. Following the convention documented in the `mosquitto` role README:

1. Pick a plaintext password.
2. Generate the hash with `mosquitto_passwd -b /tmp/mq.passwd foxess-bridge <plaintext>`.
3. On the runner host (`/pve/secrets/mosquitto.sh`), add:

   ```bash
   export MOSQUITTO_HASH_FOXESS_BRIDGE='$7$101$...'
   export MOSQUITTO_PASSWORD_FOXESS_BRIDGE='<plaintext>'
   ```

4. Re-apply both the broker (`./run/execute_runner ansible_lxc 212`) and the bridge host (`./run/execute_runner ansible_vm 214`) so each side ends up with the matching half of the credential.

## Wiring the Energy dashboard (manual HA step)

Discovered sensors are not auto-added to the Energy dashboard. In **Settings → Dashboards → Energy**:

- **Solar panels → Add solar production:** `PV Energy`.
- **Home battery storage → Add battery system:** `Battery Charge Energy` as energy going in, `Battery Discharge Energy` as energy coming out.
- **Electricity grid → Add return:** `Grid Export Energy`.
- **Grid consumption:** keep the smart-meter statistic from `glow_energy_importer` — it is the billed figure. Do not also add `Grid Import Energy`, or import is counted twice.

## Verifying the bridge

```bash
# On any host with mosquitto-clients, watching all FoxESS topics:
mosquitto_sub -h mosquitto.home.matagoth.com -u homeassistant -P '<plaintext>' \
              -t 'foxess/#' -v

# On the bridge host, looking at the daemon journal:
./run/host-ssh 214 journalctl -u foxess-mqtt-bridge -f
```

Expect a `polling <model> device …<last-4-of-serial> every 120s` line at start-up, `online` on the availability topic, one retained `homeassistant/sensor/foxess_<serial>_<key>/config` per sensor, and a `foxess/<serial>/state` JSON update every `poll_interval` seconds. The values should match the FoxCloud app.

## Tests

Pure-logic unit tests (request signing, the data-timestamp parser, and the state mapping with its lifetime-counter guard) live under `tests/` and need no dependencies — the network deps are stubbed:

```bash
cd ansible/roles/foxess_mqtt_bridge && python3 -m unittest discover -s tests
```

## Notes

- The Open API signature joins path, token and timestamp with the four literal characters `\r\n`, not a CRLF. A real CRLF produces `errno 40256` (illegal signature).
- The cloud occasionally serves a lifetime counter as zero or an older value. HA reads any drop in a `total_increasing` sensor as a meter reset and re-adds the whole counter on recovery, so the daemon holds a counter at its last good value rather than let it go backwards. The guard is in-memory: a genuine counter reset (e.g. a replaced inverter) takes effect on the next daemon restart.
- The lifetime counters have 0.1 kWh resolution, so hourly Energy-dashboard bars are quantised to that step.
- `retain=True` on the state topic means HA shows the last known reading immediately after a restart, rather than waiting for the next poll.
- Discovery is re-published on every MQTT (re)connect so a wiped broker (e.g. `mosquitto.db` deleted) recovers without manual intervention.
