# moebius

Deploys moebius, the receiver for the ffxiv repository's Dalamud exporter plugin, on its own LXC. The plugin on the desktop POSTs a snapshot of the logged-in character; readers such as `tools/character.py` on the laptop fetch them back. What moebius does, its API and its retention are in its own repository (`matagoth-zaibatsu/moebius`, `README.md`); this README covers how it is deployed.

## The host's fence

A table of the role's own, `inet ingress`, on the input hook (no Docker here, so no forward chain):

- **The API port (8080)** to the reverse proxy alone. The proxy terminates TLS for `moebius.homelab.matagoth.com` and applies the catalogue's `allow` list, the laptop and the desktop. Nothing reaches the plain-HTTP port directly.
- **The metrics port (9102) and node_exporter (9100)** to Prometheus alone. Metrics have a port of their own so that the proxy's route to the API does not expose them.
- **SSH** to the usual sources.

Everything else is dropped, and the drops are recorded by source in the `observed_input` set.

## Installing a release

`moebius_version`, `moebius_commit` and `moebius_sha256` pin a release on the forge. When the installed binary's sha256 differs from the pin, the converge, **on the apply runner** and with `forge-deploy`'s read-only token from `/pve/secrets/moebius.sh`:

1. checks that the tag `v<version>` points at the pinned commit;
2. downloads the release's `moebius-<version>-linux-amd64` asset, refusing it unless its sha256 is the pinned one;
3. copies it to this host and restarts the service.

220 never holds a forge credential. Downloading a release asset needs the releases unit on the `deploy` team, not only the code unit; see the post-deploy-setup runbook.

To move to a new release, take the version, commit and sha256 from the release page (the `.sha256` asset holds the last), bump all three and converge. The converge waits for `/healthz` to report the new version.

## What lives where

| Path | Owner, mode | Contents |
|------|-------------|----------|
| `/usr/local/bin/moebius` | root `0755` | The pinned release's binary |
| `/etc/moebius/env` | root `0600` | The write and read tokens and the listen addresses, the unit's `EnvironmentFile` |
| `/var/lib/moebius/` | moebius `0750` | `index.db` (SQLite) and `snapshots/<snapshot_id>.json.gz`; a bind mount of `/zpool/moebius` on PVE |
| `/etc/systemd/system/moebius.service` | root `0644` | Runs as `moebius`, with a read-only root but for the data directory |
| `/etc/nftables.d/ingress.nft` | root | The inbound table, loaded by `ingress-firewall.service` before moebius starts |

The data lives in `/zpool/moebius` on PVE, so it survives the container being rebuilt. It is not backed up beyond that, and the mount is excluded from PVE backups (`backup=0`), as for the other bind-mounted datasets.

## Logs

One line per upload, with the result, the trigger and the snapshot id:

```bash
./run/host-ssh 220 'journalctl -u moebius --since -24h'
```

## Secrets

`/pve/secrets/moebius.sh` on the apply runner exports `MOEBIUS_FORGE_TOKEN`, `MOEBIUS_WRITE_TOKEN` and `MOEBIUS_READ_TOKEN`. How each is made is in the [post-deploy-setup runbook](../../../docs/runbooks/post-deploy-setup.md#moebius).
