# mosquitto

Eclipse Mosquitto MQTT broker role.

## Description

Installs and configures Mosquitto from the Debian package archive. Configures a single plaintext listener on port `1883/tcp`, with username/password authentication against a hashed password file. Persistence is enabled so retained messages (such as Home Assistant MQTT discovery payloads) survive restarts.

TLS is intentionally not configured. The codeowner accepts plaintext on the LAN for now; adding TLS later is a config-file change plus a second listener on `8883/tcp`, without disrupting existing clients.

## Tasks

- Installs `mosquitto` and `mosquitto-clients`.
- Removes Mosquitto's default listener config (which only listens on localhost).
- Templates the homelab listener config under `/etc/mosquitto/conf.d/homelab.conf`.
- Templates the password file under `/etc/mosquitto/passwd` with hashes pulled from the runner's environment.
- Ensures the persistence directory exists.
- Enables and starts the service.

## Requirements

- Debian-based OS.

## Variables

| Name | Description |
|---|---|
| `mosquitto_users` | List of broker users. Each entry has a `name` (the MQTT username) and a `password_hash_env` (the name of the runner env var that holds the hash). |

The password hashes are not stored in this repository. They are generated once per user and stored in `/pve/secrets/mosquitto.sh` on the runner host as `export MOSQUITTO_HASH_<USER>=...`.

## Generating a password hash

Mosquitto stores passwords as PBKDF2-SHA512 with a per-user salt (the `$7$...` format). The broker holds the **hash**; clients authenticate with the **plaintext**. Both halves of the credential have to be stored on the runner so the broker and its clients are deployed consistently.

To set up a new user:

1. Pick a plaintext password.
2. Generate the corresponding hash:

   ```bash
   # On any machine with mosquitto-clients installed:
   touch /tmp/mq.passwd
   mosquitto_passwd -b /tmp/mq.passwd <username> <plaintext-password>
   cat /tmp/mq.passwd     # shows: <username>:$7$...
   rm /tmp/mq.passwd
   ```

3. Add **both** the hash and the plaintext to `/pve/secrets/mosquitto.sh` on the runner host:

   ```bash
   # Server side — used by the mosquitto role to template /etc/mosquitto/passwd
   export MOSQUITTO_HASH_HOMEASSISTANT='$7$101$...'
   export MOSQUITTO_HASH_PI_01='$7$101$...'

   # Client side — used by client roles (switchbot_bridge, the HA stack)
   # to authenticate with the broker
   export MOSQUITTO_PASSWORD_HOMEASSISTANT='<plaintext>'
   export MOSQUITTO_PASSWORD_PI_01='<plaintext>'
   ```

The mosquitto role reads the `MOSQUITTO_HASH_*` vars at apply time and templates them into `/etc/mosquitto/passwd` on the broker. Client roles read the matching `MOSQUITTO_PASSWORD_*` vars and place them on the client host (typically as a `0640`-mode file, never as a process argument or env var visible to `ps`).

If you ever need to rotate a password, regenerate the hash from a new plaintext, update both env vars in lockstep, and re-run `ansible_lxc 212` plus the relevant client (`ansible_external_host pi-01`, etc.).

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - role: mosquitto
      vars:
        mosquitto_users:
          - name: homeassistant
            password_hash_env: MOSQUITTO_HASH_HOMEASSISTANT
          - name: pi-01
            password_hash_env: MOSQUITTO_HASH_PI_01
```

## Verifying the broker

From any host on the LAN with `mosquitto-clients`:

```bash
# Subscribe in one terminal
mosquitto_sub -h mosquitto.home.matagoth.com -u homeassistant -P '<plaintext>' -t 'test/#' -v

# Publish from another
mosquitto_pub -h mosquitto.home.matagoth.com -u homeassistant -P '<plaintext>' -t test/hello -m world
```

The subscriber should print `test/hello world`. The broker also publishes runtime stats under `$SYS/#` which the same `mosquitto_sub` invocation can subscribe to.

## Notes

- No reverse-proxy entry: MQTT is not HTTP and the LAN-side proxy does not handle it. Clients connect to `mosquitto.home.matagoth.com:1883` directly.
- No Prometheus scrape: Mosquitto does not expose Prometheus metrics natively. If monitoring is wanted later, add `mosquitto_exporter` (sidecar) and wire the prometheus role accordingly.
- The persistence directory survives across role re-runs. To wipe retained state (for example, to clear stale HA discovery topics), `systemctl stop mosquitto && rm /var/lib/mosquitto/mosquitto.db && systemctl start mosquitto` on the LXC.
