# forgejo

Installs Forgejo as a native binary with a SQLite backend and a systemd unit.

## What lives where

| Path | Contents |
|------|----------|
| `/usr/local/bin/forgejo` | The Forgejo binary, version pinned via `forgejo_version` |
| `/etc/forgejo/app.ini` | Configuration, templated from `app.ini.j2` |
| `/etc/forgejo/secrets.env` | Generated once on first apply; loaded by systemd via `EnvironmentFile` |
| `/mnt/forgejo/data/` | Repositories, SQLite database, LFS storage — lives on the bind-mounted `/zpool/forgejo` dataset |
| `/var/log/forgejo/` | Logs |

`/etc/forgejo/secrets.env` is generated on first apply with `openssl rand` and persisted on the LXC rootfs. The role does not regenerate it on subsequent applies — rotating the secrets would invalidate all existing sessions and 2FA tokens.

## Ports

- `3000/tcp` — Forgejo HTTP, bound to all interfaces. Fronted by `nginx_reverse_proxy` at `forge.homelab.matagoth.com` for TLS. Prometheus scrapes `/metrics` on this port.
- `2222/tcp` — Forgejo's embedded SSH server for git operations. The host's own SSH on port 22 remains untouched.

## Post-deploy steps

After first apply, create the admin user and the initial state repos via `forgejo` admin CLI:

```bash
ssh root@10.20.1.216
su - git -c '/usr/local/bin/forgejo admin user create \
  --username matagoth \
  --email wiktordepina@gmail.com \
  --random-password \
  --admin \
  --config /etc/forgejo/app.ini'

su - git -c '/usr/local/bin/forgejo admin user create \
  --username agent-bot \
  --email agent-bot@home.matagoth.com \
  --random-password \
  --config /etc/forgejo/app.ini'
```

The random passwords are printed to stdout once — capture them. The admin user goes through the web UI from `https://forge.homelab.matagoth.com` to create the three initial state repos (`hermes-skills`, `hermes-memory`, `hermes-config`) under `agent-bot`'s ownership, and to upload the Hermes LXC's SSH public key as a deploy key on each.

## Upgrading

Bump `forgejo_version` in `defaults/main.yaml`. The role downloads the new binary in-place; the handler restarts the service. Forgejo's schema migrations run automatically on start. Check the upstream release notes for breaking changes before bumping across major versions.
