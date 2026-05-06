# switchbot_bridge

BLE-to-MQTT bridge for SwitchBot Meters (`WoSensorTH`).

## Description

Installs a small Python daemon that listens passively for SwitchBot BLE advertisements, decodes the temperature / humidity / battery payload, and republishes the readings to MQTT in Home Assistant discovery format. Each meter appears in HA as a single device with three sensors (temperature, humidity, battery).

The bridge does not pair with the meters and does not poll them. It only listens, so meter battery life is unaffected.

## Tasks

- Installs `python3-venv` and `bluez`.
- Creates a system user `switchbot-bridge` and adds it to the `bluetooth` group.
- Builds a Python virtual environment under `/opt/switchbot-bridge/venv`.
- Installs `bleak`, `paho-mqtt`, and `PyYAML` from the pinned `requirements.txt`.
- Drops the daemon at `/opt/switchbot-bridge/switchbot_bridge.py`.
- Templates `/etc/switchbot-bridge/config.yml` with broker details and the MAC→friendly-name map.
- Drops the MQTT plaintext password at `/etc/switchbot-bridge/mqtt_password` (mode 0640, group readable by `switchbot-bridge`).
- Installs and enables a systemd unit with the standard hardening directives (no new privileges, protected system, private tmp, etc.).

## Requirements

- Debian-based OS (Raspberry Pi OS Lite tested).
- A working Bluetooth adapter (built-in for RPi 4B).
- An MQTT broker reachable from the host (this homelab's `mosquitto` LXC).

## Variables

| Name | Required | Default | Description |
|---|---|---|---|
| `switchbot_bridge_mqtt_host` | yes | — | Broker hostname or IP. |
| `switchbot_bridge_mqtt_port` | no | `1883` | Broker port. |
| `switchbot_bridge_mqtt_username` | yes | — | Username on the broker. |
| `switchbot_bridge_mqtt_password_env` | yes | — | Name of the env var on the runner that holds the **plaintext** password (the broker stores the corresponding hash; see the `mosquitto` role README). |
| `switchbot_bridge_mqtt_client_id` | no | `<hostname>-switchbot-bridge` | MQTT client ID. |
| `switchbot_bridge_discovery_prefix` | no | `homeassistant` | HA's MQTT discovery prefix. |
| `switchbot_bridge_state_topic_prefix` | no | `switchbot` | Top-level prefix for state and availability topics. |
| `switchbot_bridge_adapter` | no | `hci0` | BLE adapter name. |
| `switchbot_bridge_scan_mode` | no | `active` | `active` or `passive`. Active is universally compatible; passive saves a small amount of power. |
| `switchbot_bridge_devices` | no | `[]` | List of `{mac, friendly_name}` entries. Devices not in this list still get published, with auto-generated names. |

## Dependencies

- `base` (apt update/upgrade).

## Example usage

```yaml
ansible:
  roles:
    - base
    - role: switchbot_bridge
      vars:
        switchbot_bridge_mqtt_host: mosquitto.home.matagoth.com
        switchbot_bridge_mqtt_username: pi-01
        switchbot_bridge_mqtt_password_env: MOSQUITTO_PASSWORD_PI_01
        switchbot_bridge_devices:
          - mac: "E8:22:5F:FF:F7:47"
            friendly_name: "Living Room Meter"
          - mac: "CA:05:48:2B:09:A4"
            friendly_name: "Bedroom Meter"
```

## How devices appear in Home Assistant

For each meter the daemon sees, three sensors are auto-discovered under one HA device:

- `Temperature` (°C, `device_class: temperature`)
- `Humidity` (%, `device_class: humidity`)
- `Battery` (%, `device_class: battery`)

The HA device's `identifiers` is `switchbot_<lowercase-mac-without-colons>`, so renaming a device's `friendly_name` later updates HA's display name without forcing a re-pair.

The bridge also publishes its own availability under `switchbot/bridge/availability` (`online` / `offline`); each sensor's discovery payload references this topic so HA marks all readings unavailable if the bridge dies.

## Identifying which meter is in which room

Meters broadcast their MAC but not their location. On first deploy, leave `switchbot_bridge_devices: []` (or omit it). All meters appear in HA as `SwitchBot <last-4-of-mac>` (e.g. `SwitchBot f747`). To map them:

1. Pick one meter, walk it to a known location, watch which `SwitchBot <xxxx>` reading changes (e.g. by warming the meter in your hand). Record the MAC tail.
2. Repeat for each meter.
3. Add entries under `switchbot_bridge_devices` in `config/external-hosts/pi-01.yml` mapping each MAC to its friendly name.
4. Re-apply: `./run/execute_runner ansible_external_host pi-01`. The daemon restarts and re-publishes discovery; HA picks up the new names.

## Verifying the bridge

```bash
# On any host with mosquitto-clients, watching all SwitchBot topics:
mosquitto_sub -h mosquitto.home.matagoth.com -u homeassistant -P '<plaintext>' \
              -t 'switchbot/#' -v

# On the pi, looking at the daemon journal:
ssh root@pi-01.home.matagoth.com journalctl -u switchbot-bridge -f
```

You should see `online` on the availability topic, `homeassistant/sensor/switchbot_<mac>_<sensor>/config` for each meter (retained, only published once), and `switchbot/<mac>/state` JSON updates each time a meter advertises.

## Notes

- The bridge filters BLE adverts by SwitchBot service UUID (`0d00` legacy, `fd3d` newer); other devices are ignored.
- The daemon uses `connect_async` + `loop_start`, so MQTT broker availability is not a startup precondition — the daemon stays up and reconnects when the broker comes back.
- Passive scanning (`switchbot_bridge_scan_mode: passive`) needs BlueZ ≥ 5.56. Default is `active` for compatibility.
- No retain on state topics would mean HA shows nothing until the next advert lands. The bridge sets `retain=True` on state so HA always sees the last reading after a restart.
