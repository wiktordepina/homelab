# Service Setup

Post-deployment manual steps for services whose first-time configuration cannot (or should not) be automated.

This document covers the bits that have to happen *after* `terraform_lxc` and `ansible_lxc` succeed — UI onboarding flows, secrets that must be generated through a web UI, integrations that need user interaction, and configuration files that the application owns at runtime (so Ansible templating would fight with it).

If a step here can reasonably be moved into IaC, it should be — treat this document as a backlog of automation candidates as much as a runbook.

---

## Home Assistant

**Container:** LXC 206 (`homeassistant`) — Home Assistant Container, deployed via the `containers` role.
**Stack:** [`config/docker/homeassistant/docker-compose.yaml`](../config/docker/homeassistant/docker-compose.yaml)
**Persistent config:** `/zpool/homeassistant` on the Proxmox host → `/mnt/homeassistant` in the LXC → `/config` in the container.

### 1. Initial onboarding

After `ansible_lxc 206` completes, browse to `http://10.20.1.206:8123` (or `http://homeassistant.home.matagoth.com:8123` once DNS is applied). HA presents a one-time onboarding wizard:

- Create the owner account.
- Set location, time zone (`Europe/London`), unit system.
- Skip the integration auto-discovery step for now — we'll do it after the reverse proxy block is in place, otherwise re-discovery will be needed once the URL changes.

### 2. Trust the reverse proxy

HA refuses to honour `X-Forwarded-For` / `X-Forwarded-Proto` headers from any host that is not in its `trusted_proxies` list. Without this, hitting `https://homeassistant.homelab.matagoth.com` returns a 400 "Loopback / private network address detected" error.

Edit `/mnt/homeassistant/configuration.yaml` (on LXC 206) and add:

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 10.20.1.10   # nginx reverse proxy (LXC 110)
```

Restart HA: **Settings → System → Restart** (or `docker restart homeassistant` on the LXC). After restart, `https://homeassistant.homelab.matagoth.com` should load.

> Why manual? HA writes to `configuration.yaml` itself (the UI persists changes there). Templating it from Ansible would clobber any UI-driven edits on the next `ansible_lxc` run.

### 3. Philips Hue integration

With `network_mode: host` already set in the docker-compose, HA can see the Hue Bridge over SSDP without any further config:

- **Settings → Devices & services → Add integration → Philips Hue**.
- HA should auto-detect the Bridge IP on the LAN.
- Press the physical link button on the Bridge when prompted.

If the Bridge does not appear in auto-discovery, add it manually using its LAN IP (find it in the pihole DHCP leases at `https://pihole.homelab.matagoth.com`).

### 4. Long-lived access token (deferred — needed for Prometheus)

Prometheus is not yet wired to scrape HA. When you want to enable it:

1. In HA: **Profile (bottom-left) → Security → Long-lived access tokens → Create token**. Name it `prometheus`. Copy the token (only shown once).
2. Store the token on the Proxmox host: append `export HA_PROM_TOKEN='<token>'` to `/pve/secrets/homeassistant.sh`.
3. Add to `ansible/roles/prometheus/files/prometheus.yaml`:
   ```yaml
   - job_name: homeassistant
     metrics_path: /api/prometheus
     scheme: http
     bearer_token: "${HA_PROM_TOKEN}"
     static_configs:
       - targets: ["10.20.1.206:8123"]
         labels:
           app: homeassistant
   ```
   (Prometheus 2.x supports env-var substitution in the bearer token field via `--enable-feature=expand-environment-variables`; alternatively use `bearer_token_file` pointing at a file the role drops in place.)
4. Re-run `ansible_lxc 210`.

### 5. Cloudflare Tunnel exposure (deferred)

Public access to `homeassistant.matagoth.com` would currently be set up manually in the Cloudflare dashboard, the same way `ntfy.matagoth.com` is. Out of scope until the tunnel config itself is moved into IaC.

---

## Adding a new entry

Use this skeleton when documenting a new service's manual setup. Keep the structure consistent so this file stays scannable:

```markdown
## <Service Name>

**Container:** LXC <vmid> (`<hostname>`) — <flavour / one-line description>.
**Stack:** [`<path>`](../<path>)
**Persistent config:** <host path> → <lxc mount> → <container mount>.

### 1. <First step>
<Why it's needed, then the exact actions.>

### 2. <Next step>
...
```

Cross-link from the relevant section of [`DOCKER_STACKS.md`](DOCKER_STACKS.md) so anyone deploying the stack lands here for follow-up steps.
