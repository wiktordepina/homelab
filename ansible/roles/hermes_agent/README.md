# hermes_agent

Installs Hermes Agent ([NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)) as a native systemd-managed service inside the LXC, fronted by Forgejo for state and LiteLLM for LLM traffic. Replaces the bespoke `mait-gateway` service on VM 6000.

## What lives where

| Path | Contents |
|------|----------|
| `/opt/hermes-agent` | Repo clone at the pinned tag. `.venv/` is populated by `uv sync`. |
| `/usr/local/bin/hermes` | Symlink to the venv binary so the CLI is on PATH. |
| `/mnt/hermes` | `HERMES_HOME` — config, sessions, memories, skills, cron, logs. Bind-mounted from `/zpool/hermes`. |
| `/etc/hermes/secrets.env` | `EnvironmentFile` for the systemd unit; LiteLLM virtual key sourced from `/pve/secrets/hermes.sh` on the runner. |
| `/etc/nftables.conf` | Firewall ruleset (see *Network posture* below). |

## Network posture

- **Inbound:** any port from the homelab subnets (`10.20.0.0/16`, the `vmbr2` VLAN ranges, and `192.168.200.0/24`). Apps the agent builds and binds on arbitrary ports are reachable without per-port firewall edits. Everything else dropped.
- **Outbound:** DNS/NTP to the homelab nameserver, the named internal services in `defaults/main.yaml`, and TCP `80`/`443` to anywhere. APT updates work; LLM traffic always goes through the LiteLLM endpoint.
- **Provider key safety:** Hermes only ever holds a LiteLLM *virtual* key. The upstream Anthropic/OpenAI/etc. keys live on the LiteLLM LXC and never reach this host.

## Pre-apply requirements

1. `/pve/secrets/hermes.sh` on the runner exports `HERMES_LITELLM_KEY=<virtual-key>`. Create the virtual key on the LiteLLM admin with a sensible monthly budget cap and conservative TPM/RPM limits before applying this role.
2. LiteLLM is on `v1.83.0` or later (April 2026 security hardening).

## Post-deploy steps

1. Generate the agent's SSH keypair as the `hermes` user:
   ```bash
   ./run/host-ssh 217 'runuser -u hermes -- ssh-keygen -t ed25519 -N "" -f /mnt/hermes/.ssh/id_ed25519 -C agent-bot@hermes'
   ./run/host-ssh 217 'cat /mnt/hermes/.ssh/id_ed25519.pub'
   ```
2. Register that public key as a *deploy key with write access* on each of `agent-bot/hermes-skills`, `agent-bot/hermes-memory`, `agent-bot/hermes-config` in Forgejo (web UI: repo → Settings → Deploy Keys → Add Key, tick "Allow write access").
3. Add `forge.home.matagoth.com:2222` to `~hermes/.ssh/known_hosts` (`ssh-keyscan -p 2222 forge.home.matagoth.com >> /mnt/hermes/.ssh/known_hosts`).
4. Initialise the three repos as git working copies under `/mnt/hermes/{skills,memories,config}` and set their remotes to `ssh://git@forge.home.matagoth.com:2222/agent-bot/hermes-<name>.git`.
5. Run an initial `hermes` interactive session to validate the config and let Hermes write any missing schema-required keys.

## Upgrading

Bump `hermes_version` in `defaults/main.yaml`. The role re-clones to the new tag and re-runs `uv sync --frozen`. The handler restarts the gateway. Review upstream release notes before crossing minor versions — Hermes is pre-1.0 and config schema changes are documented in the release notes.

## Gaps from `mait-gateway`

See `~/Documents/hermes_adoption/README.md` for the full inventory. The high-priority ones — output sanitiser and Prometheus `/metrics` exporter — are not in this PR.
