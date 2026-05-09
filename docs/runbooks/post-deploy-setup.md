# Post-deploy service setup

This runbook records the manual steps that have to happen *after* a service has been provisioned and configured by IaC, before the service is fully usable. It exists because some configuration cannot — or should not — be expressed as code in this repository.

If a step here can reasonably be moved into IaC, it should be. Treat the contents of this document as a backlog of automation candidates as much as a procedural reference.

## What belongs here

A manual step belongs in this document when at least one of the following is true:

- **The service owns its own configuration at runtime.** Some services persist their configuration in files they manage themselves (writing to disk in response to UI actions). Templating those files from Ansible would clobber the service's own writes on the next apply. The right answer is to do the initial configuration through the service's UI and document it.
- **Onboarding requires an interactive flow.** Account creation, owner setup, location and time zone selection, an admin password set in the UI: these are first-run flows that have no IaC equivalent.
- **A secret is generated through the service's UI.** Long-lived API tokens and similar credentials are issued through web UIs and shown only once. Capturing the value and storing it in the homelab's secrets requires a human in the loop.
- **An integration requires user interaction at the device.** Pairing a hub, pressing a physical link button, scanning a QR code — these cannot be automated regardless of how thorough the IaC is.

A manual step does **not** belong here when it could be expressed as a role variable, a template, or a one-time task in a configuration role. Those are bugs to fix, not entries to document.

## Format for new entries

Each service's section should be self-contained. The header identifies the service and the container it runs in. The body lists steps in order, with each step naming what it does, why it cannot be automated, and what you need to do.

Steps that are deferred — known to be needed eventually but not done yet (for example, wiring monitoring once the service has a stable token) — are marked as such with a note about what triggers them. The codeowner prefers explicit deferral over silent skipping: "we will do this later" is a useful operational state.

Steps that are *automation candidates* — things that *could* be in IaC with effort but the codeowner has not yet committed to — are marked as such, so the document also functions as a backlog.

## Worked example: home assistant

This section is the canonical example of the format. It is also the only entry currently needed; new entries follow the same structure.

### What the service is

Home Assistant runs as a docker container deployed via the `containers` Ansible role from the stack at `config/docker/homeassistant/`, in a dedicated LXC (206) at `10.20.1.206`. It uses host networking so that local-discovery protocols (SSDP, mDNS) work for device pairing.

Persistent config flow: `/zpool/homeassistant` on the Proxmox host → `/mnt/homeassistant` in the LXC → `/config` in the container.

### 1. Initial onboarding (interactive)

After `ansible_lxc 206` completes, browse to `http://10.20.1.206:8123` (or `http://homeassistant.home.matagoth.com:8123` once DNS is applied). HA presents a one-time onboarding wizard:

- Create the owner account.
- Set location, time zone (`Europe/London`), unit system.
- Skip the integration auto-discovery step until after the trusted-proxies configuration is in place; otherwise integrations bind to the wrong external URL and have to be re-paired.

### 2. Trust the reverse proxy

Until the service knows it is behind the proxy, it rejects forwarded headers and returns a 400 "Loopback / private network address detected" error when reached through the proxy hostname.

Edit `/mnt/homeassistant/configuration.yaml` (on LXC 206) and add:

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 10.20.1.10   # nginx reverse proxy (LXC 110)
```

Restart HA: **Settings → System → Restart** (or `docker restart homeassistant` on the LXC). After restart, `https://homeassistant.homelab.matagoth.com` should load.

This is *not an automation candidate* in its current form because HA writes to `configuration.yaml` itself (the UI persists changes there). Templating it from Ansible would clobber any UI-driven edits on the next `ansible_lxc` run. The right fix in the long run is to use HA's environment-variable form of the same setting, if upstream offers one.

### 3. Philips Hue integration (interaction at the device)

With `network_mode: host` already set in the docker-compose, HA can see the Hue Bridge over SSDP without any further config:

- **Settings → Devices & services → Add integration → Philips Hue**.
- HA should auto-detect the Bridge IP on the LAN.
- Press the physical link button on the Bridge when prompted.

If the Bridge does not appear in auto-discovery, add it manually using its LAN IP (find it in the pihole DHCP leases at `https://pihole.homelab.matagoth.com`). There is no IaC equivalent — pairing requires the physical button press.

### 4. Long-lived access token for monitoring (deferred)

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

This is *deferred* until monitoring is wired up, and is an *automation candidate* if upstream ever offers a non-interactive way to mint a service token.

### 5. Cloudflare Tunnel exposure (deferred)

Public access to `homeassistant.matagoth.com` is currently set up manually in the Cloudflare dashboard, the same way `ntfy.matagoth.com` is. See [concepts/domains-and-tls](../concepts/domains-and-tls.md) for context. This step is deferred and is an *automation candidate* when the tunnel routing itself moves into IaC.

## NetAlertX

### What the service is

NetAlertX runs as a docker container deployed via the `containers` Ansible role from the stack at `config/docker/netalertx/`, in a dedicated LXC (213) at `10.20.1.213`. It uses host networking so that ARP-based discovery can reach every interface the LXC has.

The container is unusual in that it has four NICs rather than the homelab's standard one. The primary `eth0` is the DMZ presence (`10.20.1.213`) and carries the default route. Three secondary interfaces attach to the VLAN-aware bridge `vmbr2` over PVE's `enp99s0`, with explicit 802.1Q tags for the management LAN, CORE, and IOT subnets. The secondary addresses follow the `<subnet>.250.<vmid>` convention. See [reference/lxc-schema](../reference/lxc-schema.md) for the schema and [reference/switch-and-ap](../reference/switch-and-ap.md) for the trunk shape on switch port 6.

Persistent config flow: `/zpool/netalertx` on the Proxmox host → `/mnt/netalertx` in the LXC → `/app/config` and `/app/db` in the container.

### 1. Configure scan subnets

NetAlertX persists its scan settings in the SQLite database it manages itself, so the configuration cannot reasonably be templated from Ansible. After `ansible_lxc 213` completes, browse to `https://netalertx.homelab.matagoth.com` (or directly to `http://10.20.1.213:20211`) and configure the four scan subnets:

- DMZ — `10.20.0.0/16` via `eth0`
- mgmt — `192.168.200.0/16` via `eth1`
- CORE — `10.10.0.0/16` via `eth2`
- IOT — `10.50.0.0/16` via `eth3`

The exact UI path is **Settings → Scan settings**, with one entry per subnet specifying the interface NetAlertX should ARP-scan from. Save and trigger an initial scan.

### 2. Acknowledge the initial alert flood

The first scan reports every device on every subnet as "new". This is expected on a first run. Walk through the device list and either acknowledge each as known, or use the bulk-acknowledge action if the UI exposes one in the version deployed. Once the baseline is set, alerts thereafter mean genuinely new or genuinely missing devices.

### 3. OPNsense DHCP reservations for the secondary NICs

The three secondary NICs come up with static IPs declared in the LXC's YAML, so they do not request DHCP. However, OPNsense's DHCP scopes are the working inventory of "what addresses are claimed on each subnet". To keep that inventory truthful, add a static-only reservation on each of mgmt, CORE, and IOT for the relevant LXC NIC MAC, mapped to the corresponding `.250.213` address. The MACs are visible from `ip -br link` inside the container after the first apply.

This step is an *automation candidate* if/when OPNsense itself moves into IaC; until then the OPNsense UI is the canonical place for the reservation list.

### 4. Notification channel

NetAlertX supports several notification channels (ntfy, email, webhook, Apprise). To route alerts through the existing ntfy LXC (202), configure an Apprise endpoint pointing at `http://10.20.1.202/netalertx-alerts` (or whichever topic name you choose). The exact UI path is **Settings → Notifications**.

This step is interactive: the channel selection, the topic name, and the alert thresholds are all UI-driven configuration that NetAlertX itself owns.

## NetBox

### What the service is

NetBox is the homelab's IPAM and source-of-truth model: prefixes, IP addresses, VLANs, devices, virtual machines, and their relationships. It runs as a multi-container docker stack deployed via the `containers` Ansible role from `config/docker/netbox/`, in a dedicated LXC (215) at `10.20.1.215`. The stack contains five services: the NetBox web app (port `8080`), an RQ worker, a Postgres database, a Redis broker (queue), and a Redis cache. Persistent state for postgres, the redis broker, and media/reports/scripts is bind-mounted from `/zpool/netbox` on the host through `/mnt/netbox` in the LXC. The redis cache is intentionally ephemeral.

NetBox is reached from a browser at `https://netbox.homelab.matagoth.com`. Behind the proxy it speaks plain HTTP on `:8080`.

### Pre-flight (one-off)

Before triggering `homelab_iac.yml` for VMID 215 the very first time:

1. **PVE host:** create the dataset and the five subdirectories the stack will mount. Postgres and the redis broker each need their own subdir; the rest follow upstream's `/opt/netbox/netbox/{media,reports,scripts}` layout. Run on PVE as root:

   ```
   zfs create zpool/netbox
   mkdir -p /zpool/netbox/{postgres,redis,media,reports,scripts}
   chown -R 999:999 /zpool/netbox/postgres
   chown -R 999:999 /zpool/netbox/redis
   chown -R 0:0 /zpool/netbox/{media,reports,scripts}
   ```

   The UID `999` matches the postgres/valkey container user; the netbox container itself runs as `netbox:root` and writes to media/reports/scripts via root-group writability.

2. **Runner secrets** in `/pve/secrets/` (or wherever the runner sources environment from). NetBox requires nine values; seven are core, two are the auto-bootstrap superuser:

   - `NETBOX_SECRET_KEY` — Django session key. Must be at least 50 characters, cryptographically random. Generate with `python -c 'import secrets; print(secrets.token_urlsafe(64))'`.
   - `NETBOX_API_TOKEN_PEPPER_1` — pepper used to hash v2 API tokens. Without this set, NetBox refuses to materialise any API token (including the one bootstrapped from `NETBOX_SUPERUSER_API_TOKEN`) and logs `⚠️ No API token was created as API_TOKEN_PEPPERS is not set`. Generate with `python -c 'import secrets; print(secrets.token_urlsafe(50))'`. Rotating this value invalidates every existing API token.
   - `NETBOX_DB_PASSWORD` — Postgres password. Used by the netbox container *and* the postgres container; both reference the same secret.
   - `NETBOX_REDIS_PASSWORD` — password for the redis broker (queue).
   - `NETBOX_REDIS_CACHE_PASSWORD` — password for the redis cache. Distinct from the broker password by upstream convention.
   - `NETBOX_SUPERUSER_NAME` — typically `admin` or your own username.
   - `NETBOX_SUPERUSER_EMAIL` — used for password-reset email and as the `From:` address on outbound mail; can be a placeholder if email is not configured.
   - `NETBOX_SUPERUSER_PASSWORD` — the initial superuser password. Plan to rotate via the UI on first login.
   - `NETBOX_SUPERUSER_API_TOKEN` — a 40-char hex string. Generate with `python -c 'import secrets; print(secrets.token_hex(20))'`. Pre-seeding it lets you script-bootstrap NetBox before logging in to issue one. Requires `NETBOX_API_TOKEN_PEPPER_1` to be set or NetBox will silently skip token creation on first boot.

   The compose file references each via `lookup('ansible.builtin.env', 'NETBOX_*')`, the same pattern as litellm and the arrs. A missing secret surfaces as an Ansible templating error before the stack ever starts.

### 1. First boot

After `terraform_lxc 215` and `ansible_lxc 215` succeed, the netbox container's startup script runs database migrations, applies static-asset collection, and creates the superuser from the `SUPERUSER_*` env vars. On first boot this routinely takes 90–180 seconds; the healthcheck has a 300s `start_period` to keep `docker compose up -d` from declaring the dependent worker dead while migrations are still running. The healthcheck polls `/login/` every 15s and only marks the container healthy after that endpoint returns 200. Postgres and the two valkey instances must all be healthy before netbox starts; the worker waits on netbox's healthcheck before starting.

If the Ansible apply fails with `dependency netbox failed to start: container netbox is unhealthy`, check whether netbox itself eventually went healthy — it usually does — and re-run the apply. The second run is a no-op for postgres/redis and lets the worker start now that netbox is past its bootstrap.

Verify all five containers are healthy:

```
docker ps --format 'table {{.Names}}\t{{.Status}}'
```

Expected output: `netbox`, `netbox-worker`, `netbox-postgres`, `netbox-redis`, `netbox-redis-cache`, all `Up ... (healthy)`.

### 2. Trust the reverse proxy

NetBox enforces `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` strictly. The compose pre-populates both with `netbox.homelab.matagoth.com`, `netbox.home.matagoth.com`, and the LXC IP. If you reach the UI through any other hostname (a Tailscale magic-DNS name, an alternative domain, etc.), the login form will POST a CSRF token and NetBox will reject it with a 403. The fix is to add the new hostname to both env vars in the compose, redeploy, and try again.

### 3. Rotate the superuser password

The superuser exists from first boot, with the password from `NETBOX_SUPERUSER_PASSWORD`. Log in at `https://netbox.homelab.matagoth.com/`, click the user menu, and change the password. The bootstrap secret is then unused; future logins use the new password. Rotate the secret in `/pve/secrets/` to match if you ever rebuild the LXC and want the bootstrap path to recreate the same user.

### 4. Seed the model

Before NetBox is useful as a source of truth, the homelab's existing topology has to be entered. The minimum viable seed:

- **Sites:** one site, "homelab", representing the rack. NetBox uses sites as a primary grouping for everything that follows.
- **VLANs:** declare VLAN 1 (management, untagged on most ports), VLAN 10 (CORE), VLAN 50 (IOT). Optionally VLAN ranges (`Cloud`, `LoT`) if you ever expand.
- **Prefixes:** the five `/16`s (`192.168.0.0/16` mgmt, `10.20.0.0/16` DMZ, `10.10.0.0/16` CORE, `10.50.0.0/16` IOT, `10.100.0.0/16` DIRECT). Each prefix is bound to its VLAN and site.
- **Virtual machines:** one entry per LXC + VM in the fleet, with the primary IP as `10.20.1.<vmid>` and the VMID stored in a custom field for searchability.
- **IP addresses:** the static reservations from OPNsense (`192.168.200.x`) and the secondary-NIC entries for any multi-homed LXC like NetAlertX (`<subnet>.250.<vmid>`).

CSV import is the path of least resistance for the prefixes and IP addresses. The MACs and hostnames are sourceable from the most recent OPNsense `config.xml` export.

This step is *interactive and slow* the first time. Budget an hour. The reward is that every subsequent question of the form "is `<ip>` in use?" or "what device owns this MAC?" has a single authoritative answer.

## Adding a new entry

When provisioning a new service that has manual setup, add a section under this runbook using the same shape as the worked example: what the service is, then a numbered or bulleted list of post-deploy steps. For each step, name what cannot be automated and why; this both helps whoever performs the procedure next and identifies which steps are temporary versus inherent.

Cross-link to this runbook from the relevant role's notes and from any reference document that introduces the service, so the manual steps are discoverable from the places where someone first encounters the service.
