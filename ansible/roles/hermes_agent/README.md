# hermes_agent

Prepares an LXC to host Hermes Agent ([NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)). Scope is **host preparation only** — package dependencies, the `hermes` system user, the bind-mounted `HERMES_HOME`, and the egress/inbound firewall. Hermes itself is installed manually post-deploy via the upstream installer so the codeowner controls the version and installation moment.

## What this role does

| Layer | Result |
|------|--------|
| APT | `git`, `ripgrep`, `ffmpeg`, `nodejs`, `npm`, `python3` (+ `pip`, `venv`), `curl`, `ca-certificates`, `nftables`. These are what the upstream installer expects on the host. |
| User | System user `hermes` with home set to `/mnt/hermes` (the bind-mounted ZFS dataset). |
| Filesystem | `/mnt/hermes` owned by `hermes:hermes`. |
| Firewall | `/etc/nftables.conf` rendered from the template, service enabled. |

What it deliberately does *not* do: install Hermes, render its `config.yaml`, render `.env`, or install a systemd unit. Those land via the upstream installer (`curl ... | bash`) at install time.

## Network posture

- **Inbound:** any port from the homelab subnets (`10.20.0.0/16`, the three `vmbr2` VLAN ranges, and `192.168.200.0/24`). Apps the agent builds and binds on arbitrary ports are reachable from the LAN without per-port firewall edits. Everything else dropped.
- **Outbound:** DNS/NTP to the homelab nameserver, the named internal services in `defaults/main.yaml`, and TCP `80`/`443` to anywhere. APT updates work; the upstream Hermes installer can reach GitHub and astral.sh.
- **Provider key safety:** LLM traffic is expected to go through LiteLLM. The role doesn't enforce this at the network layer beyond making LiteLLM the obvious path — the upstream provider FQDNs are reachable on `443` if you point Hermes at them directly. The intended posture is that Hermes only ever holds a LiteLLM virtual key; upstream provider keys live on the LiteLLM LXC.

## Post-deploy: install Hermes

After `terraform_lxc 217 apply` + `ansible_lxc 217` and `host-key-push 217`:

```bash
./run/host-ssh 217 'runuser -u hermes -- bash -lc "
  cd ~ &&
  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/<tag>/scripts/install.sh | bash
"'
```

Replace `<tag>` with the pinned release (latest at time of writing: `v2026.5.7`). Pulling from `main` is upstream's documented path but defeats reproducibility; prefer pinning.

Once installed, configure:
- `~/.hermes/.env` — `HERMES_LITELLM_KEY` from the LiteLLM admin (virtual key with a sensible monthly budget and TPM/RPM caps).
- `~/.hermes/config.yaml` — LLM base URL at `http://10.20.1.207:4000`, model of choice, `terminal.backend: docker`, `approval.mode: manual`.

## Gaps from `mait-gateway`

See `~/Documents/hermes_adoption/README.md` for the inventory. The high-priority items (output sanitiser, Prometheus `/metrics` exporter) are not in this PR.
