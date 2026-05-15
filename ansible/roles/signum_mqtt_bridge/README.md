# signum_mqtt_bridge

Signum pool + account stats to MQTT bridge.

## Description

Installs a small Python daemon that periodically polls two HTTPS endpoints — the configured Signum pool's `getMiner/<id>` JSON API and a Signum node's `getAccount` API — and republishes the parsed metrics to MQTT in Home Assistant discovery format. Each account appears in HA as a single device with separate sensors for pool mining state and on-chain account balances.

The daemon does no mining; it only observes. The Signum miner itself (the `signum_miner` role) exposes no monitoring endpoint, so the pool's view is the best available external signal.

## Tasks

- Installs `python3-venv` and `python3-packaging`.
- Creates a system user `signum-mqtt-bridge`.
- Builds a Python virtual environment under `/opt/signum-mqtt-bridge/venv`.
- Installs `paho-mqtt`, `requests`, and `PyYAML` from the pinned `requirements.txt`.
- Drops the daemon at `/opt/signum-mqtt-bridge/signum_mqtt_bridge.py`.
- Templates `/etc/signum-mqtt-bridge/config.yml` with the account ID, endpoint URLs, and MQTT broker details.
- Drops the MQTT plaintext password at `/etc/signum-mqtt-bridge/mqtt_password` (mode `0640`, group-readable by `signum-mqtt-bridge`).
- Installs and enables a systemd unit with the standard hardening directives.

## Requirements

- Debian-based OS with outbound HTTPS to the pool and node URLs.
- An MQTT broker reachable from the host (this homelab's `mosquitto` LXC).
- A broker user dedicated to the bridge (see *MQTT credential* below).

## Variables

| Name | Required | Default | Description |
|---|---|---|---|
| `signum_mqtt_bridge_account_id` | yes | — | Numeric Signum account ID (the long form, not the `S-XXXX-…` form). |
| `signum_mqtt_bridge_pool_url` | no | `https://pool.signumcoin.ro` | Base URL of the Signum pool. The daemon hits `<url>/api/getMiner/<account>`. |
| `signum_mqtt_bridge_node_url` | no | `https://wallet.signumcoin.ro` | Base URL of a Signum node exposing the standard BRS API. The daemon hits `<url>/api?requestType=getAccount&account=<account>`. |
| `signum_mqtt_bridge_poll_interval` | no | `60` | Seconds between polls. Signum block time is ~4 minutes; 60 s is generous. |
| `signum_mqtt_bridge_http_timeout` | no | `10` | Per-request timeout in seconds. |
| `signum_mqtt_bridge_mqtt_host` | yes | — | Broker hostname or IP. |
| `signum_mqtt_bridge_mqtt_port` | no | `1883` | Broker port. |
| `signum_mqtt_bridge_mqtt_username` | yes | — | Username on the broker. |
| `signum_mqtt_bridge_mqtt_password_env` | yes | — | Name of the env var on the runner that holds the **plaintext** password (the broker stores the corresponding hash; see the `mosquitto` role README). |
| `signum_mqtt_bridge_mqtt_client_id` | no | `<hostname>-signum-mqtt-bridge` | MQTT client ID. |
| `signum_mqtt_bridge_discovery_prefix` | no | `homeassistant` | HA's MQTT discovery prefix. |
| `signum_mqtt_bridge_state_topic_prefix` | no | `signum` | Top-level prefix for state and availability topics. |

## Dependencies

- `base` (apt update/upgrade).

## Example usage

```yaml
ansible:
  roles:
    - base
    - role: signum_mqtt_bridge
      vars:
        signum_mqtt_bridge_account_id: "3033777005113980426"
        signum_mqtt_bridge_mqtt_host: mosquitto.home.matagoth.com
        signum_mqtt_bridge_mqtt_username: signum-bridge
        signum_mqtt_bridge_mqtt_password_env: MOSQUITTO_PASSWORD_SIGNUM_BRIDGE
```

## How the account appears in Home Assistant

For each account the daemon polls, the following sensors auto-discover under a single HA device named `Signum <account-id>`:

**Pool (state topic `signum/<account-id>/pool`)**

- `Total Capacity` (TiB)
- `Effective Capacity` (TiB) — capacity after the boost factor is applied
- `Commitment per TiB` (SIGNA)
- `Committed Balance` (SIGNA)
- `Boost` (factor, dimensionless — most recent value of the pool's rolling sample)
- `Pending Balance` (SIGNA, pool-side accrued)
- `Pool Share` (`sharePercent`, %)
- `Shared Capacity` (the account's fraction of the pool's effective capacity, %)
- `Confirmed Deadlines` (count this round)
- `Current Round Best Deadline` (seconds)
- `Miner User Agent` (diagnostic — e.g. `signum-miner/2.0.0`; lets you spot if the miner has crashed and is no longer submitting)
- `Pool Last Update` (timestamp)

**Account (state topic `signum/<account-id>/account`)**

- `Total Balance` (SIGNA, `balanceNQT` / 1e8)
- `Available Balance` (SIGNA, `unconfirmedBalanceNQT`)
- `Guaranteed Balance` (SIGNA, `guaranteedBalanceNQT`)
- `Forged Balance` (SIGNA, cumulative; `forgedBalanceNQT`)
- `Account Last Update` (timestamp)

The bridge also publishes its own availability under `signum/bridge/availability` (`online` / `offline`); each sensor's discovery payload references this topic so HA marks all readings unavailable if the bridge dies. A frozen `Pool Last Update` or `Account Last Update` indicates a one-sided poll failure while the bridge itself is healthy.

## MQTT credential

A dedicated broker user keeps the bridge's blast radius small. Following the convention documented in the `mosquitto` role README:

1. Pick a plaintext password.
2. Generate the hash with `mosquitto_passwd -b /tmp/mq.passwd signum-bridge <plaintext>`.
3. On the runner host (`/pve/secrets/mosquitto.sh`), add:

   ```bash
   export MOSQUITTO_HASH_SIGNUM_BRIDGE='$7$101$...'
   export MOSQUITTO_PASSWORD_SIGNUM_BRIDGE='<plaintext>'
   ```

4. Re-apply both the broker (`./run/execute_runner ansible_lxc 212`) and the bridge host (`./run/execute_runner ansible_vm 214`) so each side ends up with the matching half of the credential.

## Verifying the bridge

```bash
# On any host with mosquitto-clients, watching all Signum topics:
mosquitto_sub -h mosquitto.home.matagoth.com -u homeassistant -P '<plaintext>' \
              -t 'signum/#' -v

# On the bridge host, looking at the daemon journal:
./run/host-ssh 214 journalctl -u signum-mqtt-bridge -f
```

Expect `online` on the availability topic, one retained `homeassistant/sensor/signum_<id>_<key>/config` per sensor (published once on connect), and a `signum/<id>/pool` plus `signum/<id>/account` JSON update every `poll_interval` seconds.

## Notes

- The daemon polls the two endpoints serially each tick; a failure on one source logs a warning and does not stop the other. The respective `*_last_update` timestamp stops advancing while a source is down.
- `boost` from `getMiner/<id>` is sometimes an array of recent samples and sometimes a scalar; the daemon takes the first element of an array (most recent reading) and publishes a single float.
- `retain=True` on state topics means HA shows the last known reading immediately after a restart, rather than waiting for the next poll.
- Discovery is re-published on every MQTT (re)connect so a wiped broker (e.g. `mosquitto.db` deleted) recovers without manual intervention.
