# glow_mqtt_bridge

UK smart-meter consumption, cost and tariff to MQTT bridge, via the Hildebrand /
Glowmarkt DCC API.

## Description

Installs a small Python daemon that authenticates against the Glowmarkt API (the
same backend the free Bright app uses), discovers the meter's data resources,
and periodically republishes each fuel's running daily total, cost and tariff to
MQTT in Home Assistant discovery format. Each fuel appears in HA as a single
device with sensors for usage, cost, standing charge and unit rate.

The daemon only observes. The data path is the DCC backend, so readings are
half-hourly and delayed (typically settling after ~01:30 for the previous day);
this is not a real-time source. For real-time local data a Glow IHD-CAD over
local MQTT would be required instead — see the plan note that accompanied this
role.

Unlike the `signum_mqtt_bridge`, the Glowmarkt API is authenticated and the
meter's resources are not known ahead of time: the auth token is cached to the
systemd `StateDirectory`, and the consumption/cost resources are discovered
after login. Electricity-only accounts simply yield no gas device.

## Tasks

- Installs `python3-venv` and `python3-packaging`.
- Creates a system user `glow-mqtt-bridge`.
- Builds a Python virtual environment under `/opt/glow-mqtt-bridge/venv`.
- Installs `paho-mqtt`, `requests`, and `PyYAML` from the pinned `requirements.txt`.
- Drops the daemon at `/opt/glow-mqtt-bridge/glow_mqtt_bridge.py`.
- Templates `/etc/glow-mqtt-bridge/config.yml` with the API endpoint, Bright
  username, poll interval, and MQTT broker details.
- Drops two plaintext secret files (mode `0640`, group-readable by
  `glow-mqtt-bridge`): the Glowmarkt account password and the MQTT password.
- Installs and enables a systemd unit with the standard hardening directives and
  a `StateDirectory` for the token cache.

## Requirements

- Debian-based OS with outbound HTTPS to the Glowmarkt API.
- An MQTT broker reachable from the host (this homelab's `mosquitto` LXC).
- A broker user dedicated to the bridge (see *MQTT credential* below).
- A **validated Bright account** with DCC data access for the meter. Registration
  is a manual, human-gated step that can take a couple of days to validate; it is
  tracked as assumed-inputs debt outside this repo.

## Variables

| Name | Required | Default | Description |
|---|---|---|---|
| `glow_mqtt_bridge_username` | yes | — | Bright account username (the email the meter is registered under). |
| `glow_mqtt_bridge_password_env` | yes | — | Name of the env var on the runner holding the **plaintext** Bright account password. |
| `glow_mqtt_bridge_api_url` | no | `https://api.glowmarkt.com/api/v0-1` | Base URL of the Glowmarkt API. |
| `glow_mqtt_bridge_application_id` | no | `b0f1b774-…-27ead8aa7a8d` | Public Bright application ID sent as the `applicationId` header. |
| `glow_mqtt_bridge_poll_interval` | no | `1800` | Seconds between polls. DCC data is half-hourly and delayed; 30 min is generous. |
| `glow_mqtt_bridge_http_timeout` | no | `15` | Per-request timeout in seconds. |
| `glow_mqtt_bridge_mqtt_host` | yes | — | Broker hostname or IP. |
| `glow_mqtt_bridge_mqtt_port` | no | `1883` | Broker port. |
| `glow_mqtt_bridge_mqtt_username` | yes | — | Username on the broker. |
| `glow_mqtt_bridge_mqtt_password_env` | yes | — | Name of the env var on the runner holding the **plaintext** MQTT password (the broker stores the hash; see the `mosquitto` role README). |
| `glow_mqtt_bridge_mqtt_client_id` | no | `<hostname>-glow-mqtt-bridge` | MQTT client ID. |
| `glow_mqtt_bridge_discovery_prefix` | no | `homeassistant` | HA's MQTT discovery prefix. |
| `glow_mqtt_bridge_state_topic_prefix` | no | `glow` | Top-level prefix for state and availability topics. |

## Dependencies

- `base` (apt update/upgrade).

## Example usage

```yaml
ansible:
  roles:
    - base
    - role: glow_mqtt_bridge
      vars:
        glow_mqtt_bridge_username: someone@example.com
        glow_mqtt_bridge_password_env: GLOW_BRIDGE_PASSWORD
        glow_mqtt_bridge_mqtt_host: mosquitto.home.matagoth.com
        glow_mqtt_bridge_mqtt_username: glow-bridge
        glow_mqtt_bridge_mqtt_password_env: MOSQUITTO_PASSWORD_GLOW_BRIDGE
```

## How the meter appears in Home Assistant

For each fuel discovered (electricity, and gas if the account is dual-fuel), the
following sensors auto-discover under a single HA device named
`Smart Meter <Fuel>`:

**State topic `glow/<fuel>/state`**

- `Usage Today` (kWh, `total_increasing` — resets nightly; feeds the Energy dashboard)
- `Cost Today` (GBP, `total_increasing`)
- `Standing Charge` (GBP)
- `Rate` (GBP/kWh)
- `Last Update` (timestamp)

The bridge also publishes its own availability under `glow/bridge/availability`
(`online` / `offline`); each sensor's discovery payload references this topic so
HA marks all readings unavailable if the bridge dies. A frozen `Last Update` on
one fuel while the bridge is healthy indicates a one-sided poll failure.

## MQTT credential

A dedicated broker user keeps the bridge's blast radius small. Following the
convention documented in the `mosquitto` role README:

1. Pick a plaintext password.
2. Generate the hash with `mosquitto_passwd -b /tmp/mq.passwd glow-bridge <plaintext>`.
3. On the runner host (`/pve/secrets/mosquitto.sh`), add:

   ```bash
   export MOSQUITTO_HASH_GLOW_BRIDGE='$7$101$...'
   export MOSQUITTO_PASSWORD_GLOW_BRIDGE='<plaintext>'
   ```

4. Re-apply both the broker (`./run/execute_runner ansible_lxc 212`) and the
   bridge host (`./run/execute_runner ansible_vm 214`) so each side ends up with
   the matching half of the credential.

## Glowmarkt credential

The Bright account password is sourced the same way as the MQTT one, from a
runner env var named by `glow_mqtt_bridge_password_env`. Add it alongside the
broker secrets on the runner (e.g. in `/pve/secrets/`):

```bash
export GLOW_BRIDGE_PASSWORD='<bright-account-password>'
```

## Verifying the bridge

```bash
# On any host with mosquitto-clients, watching all glow topics:
mosquitto_sub -h mosquitto.home.matagoth.com -u homeassistant -P '<plaintext>' \
              -t 'glow/#' -v

# On the bridge host, looking at the daemon journal:
./run/host-ssh 214 journalctl -u glow-mqtt-bridge -f
```

Expect `online` on the availability topic, one retained
`homeassistant/sensor/glow_<fuel>_<key>/config` per sensor (published once on
connect), and a `glow/<fuel>/state` JSON update every `poll_interval` seconds.

## Notes

- DCC readings are delayed. `Usage Today` is `0`/`null` early in the day and
  firms up as the DCC backfills; this is expected, not a fault.
- **Tariff may lag the meter going live.** On a freshly-validated account the
  `tariff` endpoint returns an empty `data` array until the DCC feed populates,
  so `Standing Charge` and `Rate` publish as `null` until then and light up
  automatically once data appears. The `currentRates.{rate, standingCharge}`
  field mapping should be re-confirmed against live tariff data when it arrives.
- The auth token is long-lived (~18 months observed) and persisted to
  `/var/lib/glow-mqtt-bridge/token.json` so restarts do not re-authenticate. A
  token revoked early triggers a single re-auth-and-retry on the next request.
- `retain=True` on state topics means HA shows the last known reading immediately
  after a restart, rather than waiting for the next poll.
- Discovery is re-published on every MQTT (re)connect so a wiped broker recovers
  without manual intervention.
