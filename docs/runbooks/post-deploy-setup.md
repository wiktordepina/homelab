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
  ip_ban_enabled: true
  # Deliberately no login_attempts_threshold. HA's default is unlimited, and a
  # finite value locks the Nabu Casa remote URL out — see "Nabu Casa remote URL
  # returns 403" below.
```

Restart HA: **Settings → System → Restart** (or `docker restart homeassistant` on the LXC). After restart, `https://homeassistant.homelab.matagoth.com` should load.

#### Nabu Casa remote URL returns 403 Forbidden

Symptom: the `*.ui.nabu.casa` URL answers `403 Forbidden` for everyone, while the LAN hostname works. Confirm with:

```sh
./run/host-ssh 206 'cat /mnt/homeassistant/ip_bans.yaml'
./run/host-ssh 206 'grep -h "http.ban" /mnt/homeassistant/home-assistant.log.1 /mnt/homeassistant/home-assistant.log | tail'
```

Expected when this is the problem: a `127.0.0.1:` entry in `ip_bans.yaml`, and log lines like
`Login attempt or request with invalid authentication from localhost (127.0.0.1). Requested URL: '/media/system/js/core.js'` followed by `Banned IP 127.0.0.1 for too many login attempts`.

Why it happens: the Nabu Casa tunnel terminates inside HA over loopback and forwards no client address, so every remote visitor — you, the companion app, and internet scanners — is `127.0.0.1` to HA. Any request answered `401` counts as a failed login for that address, the counter is cumulative for the life of the process, and the Nabu Casa hostname is discoverable through certificate-transparency logs, so scanners probing for CMS paths hit it regularly. With `login_attempts_threshold` set, loopback is eventually banned and the whole remote path goes dark. Adding `127.0.0.1` to `trusted_proxies` does nothing here: there is no forwarded header to trust.

Recover:

```sh
./run/host-ssh 206 'sed -i "/^127\.0\.0\.1:/,/banned_at/d" /mnt/homeassistant/ip_bans.yaml && docker restart homeassistant'
```

The restart is required — bans are loaded into memory at startup and editing the file alone does not lift one. Then make sure `login_attempts_threshold` is absent from the `http:` block, otherwise it will happen again. The ban feature cannot protect the Nabu Casa path (it can only ever ban loopback), so nothing is lost; for real brute-force protection enable TOTP MFA on the owner account under **Profile → Security**.

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

## Forgejo

### What the service is

Forgejo runs as a native binary in LXC 216 at `10.20.1.216`, configured by the `forgejo` Ansible role, and hosts the git repositories that are not on GitHub. Forgejo Actions runs their CI on the runners in 501 and 502 — see [create-runner](create-runner.md) for that pairing, which is a separate procedure.

### 1. The organisation and the `ci` team

Repositories that carry CI live in the `matagoth-zaibatsu` organisation, not under the `matagoth` user. The reason is `forge-ci` (below): it is not an admin and every repository is private, so it must be granted access explicitly, and an organisation team is where those grants live. They are deliberately made one repository at a time rather than inherited by every repository, because a team's access is only as contained as the token that carries it.

Organisations cannot be created by the `forgejo` role — the local admin CLI has no equivalent of `admin user create` for them, and the API needs a token the role does not hold. `app.ini` stops non-admins creating organisations, but `matagoth` is an admin, so this is a manual step rather than a configuration change.

**Create the organisation**, signed in as `matagoth`:

```bash
curl -X POST \
  -H "Authorization: token <matagoth-token>" \
  -H 'Content-Type: application/json' \
  -d '{"username":"matagoth-zaibatsu","visibility":"private"}' \
  https://forge.homelab.matagoth.com/api/v1/orgs
```

**Create the `ci` team.** It covers **no** repository by default; each repository whose workflows use `FORGE_CI_TOKEN` is added to it explicitly.

```bash
curl -X POST \
  -H "Authorization: token <matagoth-token>" \
  -H 'Content-Type: application/json' \
  -d '{
        "name":"ci",
        "description":"forge-ci: opens the pull requests the automatic job token cannot",
        "permission":"write",
        "includes_all_repositories":false,
        "can_create_org_repo":false,
        "units":["repo.code","repo.pulls"]
      }' \
  https://forge.homelab.matagoth.com/api/v1/orgs/matagoth-zaibatsu/teams
# note the team id in the response
```

Code and pulls are what `forge-ci` uses: it opens pull requests. Releases are left out because nothing needs them, not because leaving them out is a control. Code write on a repository with Actions enabled already includes Releases: a pushed branch can carry a workflow, and the automatic job token can create a Release (section 2). In `fin_hub`, where the Release rather than the tag is what deploys, that means **anyone with code write can create a Release for an existing tag**, including one `release-publish.yml` refused. The control for that is on the deploying side, which must verify the tag signature itself rather than trust that a Release exists. Until it does, code write on `fin_hub` is deploy access, and is granted accordingly.

What keeping `ci` to named repositories buys is containment: the token is readable by every workflow on a repository that holds it, and a leaked copy reaches the repositories in this team and no others.

On a forge where the team already exists covering every repository, or with the releases unit, narrow it in place. **`permission` must be in the body.** The edit endpoint only reads `includes_all_repositories` when `permission` is also sent, and without it the call still answers `200`, applies the units and silently leaves the flag on:

```bash
curl -X PATCH \
  -H "Authorization: token <matagoth-token>" \
  -H 'Content-Type: application/json' \
  -d '{"name":"ci","permission":"write","includes_all_repositories":false,"units":["repo.code","repo.pulls"]}' \
  https://forge.homelab.matagoth.com/api/v1/teams/<ci-team-id> \
  | jq '{includes_all_repositories, units}'
# {"includes_all_repositories": false, "units": ["repo.code", "repo.pulls"]}
```

Turning the flag off keeps every repository the team was already linked to. Remove each one that does not use the token (each call returns `204`):

```bash
curl -X DELETE \
  -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/teams/<ci-team-id>/repos/matagoth-zaibatsu/<repo>
```

Then list what is left. It should be exactly the repositories that hold `FORGE_CI_TOKEN`:

```bash
curl -s -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/teams/<ci-team-id>/repos | jq -r '.[].full_name'
# matagoth-zaibatsu/fin_hub
```

**Add `forge-ci` to it, and the repositories that use its token** — today only `fin_hub` — using the team id returned above:

```bash
curl -X PUT \
  -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/teams/<team-id>/members/forge-ci

curl -X PUT \
  -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/teams/<team-id>/repos/matagoth-zaibatsu/fin_hub
```

A repository that starts using `FORGE_CI_TOKEN` needs both: the secret on the repository (section 2) and the repository in this team. Either alone fails with a `403`/`404` from the pull-request call.

`forge-ci` should be the team's only member. A human added here would be granted through CI's path rather than their own, which makes an audit of either one meaningless.

**Create the `agents` team** for `matabot`, the account Claude Code works as from the workstation. It is a team of its own rather than a second member of `ci`, for the same audit reason, and unlike `ci` it covers **no** repository by default: `matabot` gets only the repositories it is explicitly given.

```bash
curl -X POST \
  -H "Authorization: token <matagoth-token>" \
  -H 'Content-Type: application/json' \
  -d '{
        "name":"agents",
        "description":"matabot: Claude Code on the workstation; repositories granted one by one",
        "permission":"write",
        "includes_all_repositories":false,
        "can_create_org_repo":false,
        "units":["repo.code","repo.pulls","repo.issues"]
      }' \
  https://forge.homelab.matagoth.com/api/v1/orgs/matagoth-zaibatsu/teams
# note the team id in the response

curl -X PUT \
  -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/teams/<agents-team-id>/members/matabot
```

The `forgejo` role creates `matabot` restricted, but its CLI cannot report the flag afterwards, so confirm it through the admin API:

```bash
curl -s -H "Authorization: token <matagoth-token>" \
  'https://forge.homelab.matagoth.com/api/v1/admin/users?limit=50' \
  | jq '.[] | select(.login=="matabot") | {login, restricted, is_admin}'
# {"login": "matabot", "restricted": true, "is_admin": false}
```

Grant a repository when the bot is to work on it:

```bash
curl -X PUT \
  -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/teams/<agents-team-id>/repos/matagoth-zaibatsu/<repo>
```

Before granting one, check two things, because write access on a repository with Actions enabled reaches further than the repository:

- **Its Actions secrets.** A branch the bot pushes can add a workflow that prints any secret the repository receives. The repository must hold no secret the bot should not have. Today that rules out `fin_hub`, which holds `FORGE_CI_TOKEN` (section 2).
- **Whether a Release deploys it.** The `agents` team has no releases unit, but that does not keep the bot from Releases: a branch it pushes can carry a workflow, and the automatic job token can create one. So a repository whose Releases deploy something must not be granted until the deploying side verifies the tag signature itself. Today that also rules out `fin_hub`.

`matabot` has no repository of its own and cannot create one; see [Creation limits](../../ansible/roles/forgejo/README.md#creation-limits).

**Create the `deploy` team** for `forge-deploy`, the read-only account hosts use to fetch private repositories they deploy (maitre-d on the workstation is the first). Read permission, the code unit only, and no repository by default:

```bash
curl -X POST \
  -H "Authorization: token <matagoth-token>" \
  -H 'Content-Type: application/json' \
  -d '{
        "name":"deploy",
        "description":"forge-deploy: hosts fetching what they deploy; read-only, repositories granted one by one",
        "permission":"read",
        "includes_all_repositories":false,
        "can_create_org_repo":false,
        "units":["repo.code"]
      }' \
  https://forge.homelab.matagoth.com/api/v1/orgs/matagoth-zaibatsu/teams
# note the team id in the response

curl -X PUT \
  -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/teams/<deploy-team-id>/members/forge-deploy

curl -X PUT \
  -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/teams/<deploy-team-id>/repos/matagoth-zaibatsu/maitre-d
```

Forgejo answers `200` to a team edit it partly ignored, so read the result back from the database rather than the response:

```bash
./run/host-ssh 216 python3 - <<'EOF'
import sqlite3
c = sqlite3.connect('file:/mnt/forgejo/data/forgejo.db?mode=ro', uri=True)
t = c.execute("select id, authorize, includes_all_repositories from team where lower_name = 'deploy'").fetchone()
print('team', t)
print('repos', c.execute('select r.name from team_repo tr join repository r on r.id = tr.repo_id where tr.team_id = ?', (t[0],)).fetchall())
print('units', c.execute('select type, access_mode from team_unit where team_id = ?', (t[0],)).fetchall())
EOF
# team (<id>, 1, 0)      authorize 1 is read; 0: not every repository
# repos [('maitre-d',)]
# units [(1, 1)]         the code unit, read
```

Then mint its token into the secrets store, the same way as `matabot`'s. `read:repository` is the only scope:

```bash
./run/host-ssh 216 "su - git -c '/usr/local/bin/forgejo --config /etc/forgejo/app.ini \
  admin user generate-access-token \
  --username forge-deploy \
  --token-name workstation-maitre-d \
  --scopes read:repository \
  --raw'" \
| ./run/pve-ssh 'read -r t && printf "export MAITRE_D_FORGE_TOKEN=%s\n" "$t" > /zpool/secrets/maitre_d.sh && chmod 0644 /zpool/secrets/maitre_d.sh'

./run/pve-ssh 'wc -c /zpool/secrets/maitre_d.sh'
# 69 /zpool/secrets/maitre_d.sh
```

**Protect `main` on every repository in the organisation**, not only those the bot is granted. Grants to `ci` and `agents` change over time, and a repository added to either must already be protected when the grant lands rather than after someone remembers. Protecting every `main` up front makes that ordering impossible to get wrong. Only `matagoth` merges:

```bash
curl -X POST \
  -H "Authorization: token <matagoth-token>" \
  -H 'Content-Type: application/json' \
  -d '{
        "rule_name":"main",
        "enable_push":false,
        "enable_merge_whitelist":true,
        "merge_whitelist_usernames":["matagoth"],
        "block_on_rejected_reviews":true,
        "dismiss_stale_approvals":true,
        "apply_to_admins":true
      }' \
  https://forge.homelab.matagoth.com/api/v1/repos/matagoth-zaibatsu/<repo>/branch_protections
```

For a repository that already has a `main` rule, send the same body (without `rule_name`) plus `"required_approvals":0` as a `PATCH` to `.../branch_protections/main`. The `PATCH` leaves fields it is not sent untouched, so an older rule's required approvals would otherwise survive and block `matagoth`'s own pull requests (see below). A pre-existing rule with `enable_push: false` but no merge allowlist only looks protected: any account with write access can open a pull request and merge it itself.

The allowlist is deliberately for **merging**, not required approvals. Forgejo does not let a pull request's author approve it, so a required approval would block `matagoth`'s own pull requests, while the merge allowlist has the intended effect: the bot proposes, and only `matagoth` lands it. Confirm the rule took:

```bash
curl -s -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/repos/matagoth-zaibatsu/<repo>/branch_protections/main \
  | jq '{enable_push, enable_merge_whitelist, merge_whitelist_usernames, apply_to_admins}'
# {"enable_push": false, "enable_merge_whitelist": true, "merge_whitelist_usernames": ["matagoth"], "apply_to_admins": true}
```

Repositories move in with a transfer. Transferring into an organisation you already own completes immediately — there is no pending invitation to accept — and issues, pull requests, releases, Actions history and existing collaborators all survive it:

```bash
curl -X POST \
  -H "Authorization: token <matagoth-token>" \
  -H 'Content-Type: application/json' \
  -d '{"new_owner":"matagoth-zaibatsu"}' \
  https://forge.homelab.matagoth.com/api/v1/repos/matagoth/<repo>/transfer
```

Forgejo leaves a redirect at the old path afterwards, so a stale git remote keeps working and gives no sign it is stale. Update remotes rather than relying on it:

```bash
git remote set-url origin ssh://git@forge.home.matagoth.com:2222/matagoth-zaibatsu/<repo>.git
```

A *new* repository has to be created in the organisation deliberately. `fj repo create` takes no owner and always creates under the signed-in user, which puts the repository back in the personal namespace and outside the team grant. Create it in the organisation instead:

```bash
curl -X POST \
  -H "Authorization: token <matagoth-token>" \
  -H 'Content-Type: application/json' \
  -d '{"name":"<repo>","private":true,"default_branch":"main"}' \
  https://forge.homelab.matagoth.com/api/v1/orgs/matagoth-zaibatsu/repos
```

Not everything belongs in the organisation. `agent-bot`'s Hermes state repositories are reached by deploy key, run no CI and never need `forge-ci`, so they stay under `agent-bot` — moving them would change Hermes' access path for no gain.

### 2. The Actions CI token

Forgejo hands every Actions job an automatic token. It is a real forge account, `forgejo-actions` (id `-2`), and its repository access **excludes the pulls unit**, so a workflow that tries to open a pull request gets:

```
POST $GITHUB_API_URL/repos/$GITHUB_REPOSITORY/pulls
404 {"message":"Can't read pulls or can't read UnitTypeCode"}
```

A `permissions:` block in the workflow changes nothing — the unit is granted on the forge, not claimed by a workflow. Pushing a branch and cutting a Release both work with the automatic token; opening a pull request is the one thing that does not.

The answer is a dedicated non-admin account, `forge-ci`, whose token is exposed to workflows as the secret `FORGE_CI_TOKEN`. The `forgejo` role creates that account and asserts it is not an admin, so only the token itself is manual — it is issued by the service and displayed once.

**Mint the token** on the Forgejo container:

```bash
./run/host-ssh 216

su - git -c '/usr/local/bin/forgejo --config /etc/forgejo/app.ini \
  admin user generate-access-token \
  --username forge-ci \
  --token-name forge-ci-actions \
  --scopes write:repository \
  --raw'
# 40 hexadecimal characters, printed once and never retrievable again
```

`write:repository` covers pulls, contents and releases, and nothing else — the token cannot read `/api/v1/user`, which is expected rather than a symptom. Add `read:user` only if something turns out to need it.

**Install it as a secret on each repository that uses it, and on no other.** Forgejo has no instance-level Actions secret; the admin panel offers global *variables* only, and the API exposes secrets at repository, organisation and user level. Today only `fin_hub` uses the token (`release-prep.yml` opens the release pull request with it):

```
https://forge.homelab.matagoth.com/matagoth-zaibatsu/fin_hub/settings/actions/secrets
```

Add a secret named `FORGE_CI_TOKEN` with the minted value. The equivalent call, signed in as `matagoth`, is:

```bash
curl -X PUT \
  -H "Authorization: token <matagoth-token>" \
  -H 'Content-Type: application/json' \
  -d '{"data":"<forge-ci-token>"}' \
  https://forge.homelab.matagoth.com/api/v1/repos/matagoth-zaibatsu/fin_hub/actions/secrets/FORGE_CI_TOKEN
```

The value is write-only afterwards. If it is ever lost, mint a new one and overwrite the secret rather than hunting for the old one — nothing else stores a copy, deliberately. A second repository that needs it gets its own copy of the same value, set the same way.

The level is the point. An **organisation** secret would be one copy reaching every repository in `matagoth-zaibatsu`, which is convenient and is how this started. But any account that can push a branch to a repository with Actions enabled can add a workflow that prints every secret that repository receives. With an organisation secret, write access on *any* organisation repository becomes `forge-ci`'s write access on every repository in the `ci` team, which is exactly the reach the `agents` team is designed to withhold from `matabot`. At repository level, the token is exposed only where it is used, and those repositories are kept out of `agents`.

A *user* secret is no better: one set on `matagoth` reaches only repositories that user owns, so it resolves to nothing once a repository is in the organisation, and a workflow whose `secrets.FORGE_CI_TOKEN` is empty fails with the same `403` shape as a badly scoped token.

Copies left at either level are a leak, not a fallback. Confirm the organisation and the `matagoth` user hold none:

```bash
curl -s -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/orgs/matagoth-zaibatsu/actions/secrets | jq -r '.[].name'
# (no output)
```

There is no API to *list* user-level secrets — `GET /api/v1/user/actions/secrets` is a 404, unlike its organisation equivalent — so check `https://forge.homelab.matagoth.com/user/settings/actions/secrets` by eye. Delete a stray copy with:

```bash
curl -X DELETE \
  -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/orgs/matagoth-zaibatsu/actions/secrets/FORGE_CI_TOKEN
# or, for a user-level copy:  .../api/v1/user/actions/secrets/FORGE_CI_TOKEN
```

Moving the token from organisation to repository level means minting a new one: the organisation secret is write-only, so its value cannot be copied across. Set the new value on each repository first, prove a workflow still opens its pull request (section 3), then delete the organisation copy.

Deleting the secret does not revoke the token it held, and **a superseded `forge-ci` token cannot be revoked without more work than it sounds**. The admin CLI generates tokens but neither lists nor deletes them, and `DELETE /api/v1/users/forge-ci/tokens/<name>` authenticates with basic auth *as `forge-ci`* — an account whose password is random and discarded at creation, so nobody holds it. Revoking one means setting a password on the account first, deleting the token with it, and letting the next converge clear the must-change-password flag that `admin user change-password` re-arms.

The consequence is worth stating rather than discovering: **minting a replacement `forge-ci` token leaves the old one live**, with identical access, until that dance is done. Rotate only when there is a reason to, not as routine hygiene.

### 3. Confirm it

The token's scope bounds what `forge-ci` *may* do; the team grant is what gives it access to anything. Both have to be right, and the check that matters is the one that fails with the automatic token. From a workflow on a repository that holds the secret:

```yaml
- name: Open a pull request with the CI token
  run: |
    code=$(curl -sS -o /tmp/pr.json -w '%{http_code}' -X POST \
      -H "Authorization: token ${{ secrets.FORGE_CI_TOKEN }}" \
      -H "Content-Type: application/json" \
      "$GITHUB_API_URL/repos/$GITHUB_REPOSITORY/pulls" \
      -d '{"title":"probe","head":"<branch>","base":"main","body":"probe"}')
    cat /tmp/pr.json
    test "$code" -lt 300
```

A 2xx and a pull request authored by `forge-ci` is the whole proof. Forgejo exposes no log-fetch API, so read the outcome from the job's own status — `fj actions tasks` lists it — which is why the probe is a step that fails loudly rather than one that prints and passes.

### On the blast radius

The runners in 501 and 502 are instance-level and shared by every repository on the forge, and jobs get no Docker socket and no bind mounts, so this token is only as isolated as those machines. The codeowner accepts that: the forge is LAN-only and every repository on it is theirs, so the blast radius is their own repositories and reaching it already requires commit access to one of them.

That last clause stopped being only the codeowner once `matabot` exists, because the bot has commit access by design. It is why the token lives on the repositories that use it rather than on the organisation, why both teams name their repositories one by one, and why every `main` admits only `matagoth`'s merges: holding the bot's access, or anything a workflow on its repositories can read, should reach no further than those repositories. It cannot be made to exclude Releases on those repositories, because code write includes them through the job token, which is why a repository whose Releases deploy is not granted to the bot until the deploying side verifies signatures.

LAN-only is not the whole of the answer, though, because the risk that survives it is egress rather than ingress. Workflows pull third-party actions from the Forgejo mirror, and a compromised mirrored action in any repository's workflow could read this secret. The runners' egress allowlist (see the [`forgejo_runner` role README](../../ansible/roles/forgejo_runner/README.md#what-the-runner-can-and-cannot-reach)) narrows where it could send it, to the handful of names CI needs. But some of those names, `github.com` among them, accept uploads, so the path is narrowed, not closed. It is still the one to watch.

## Claude Code workstation

### What the service is

A VM (218) where Claude Code runs as the unprivileged `agent` user under root-owned managed settings, configured by the `claude_workstation` role. It works on forge repositories as `matabot`. The role README covers what the settings enforce and why.

Three things the role cannot do: mint `matabot`'s token, log Claude Code in, and grant the bot repositories.

### 1. Mint the bot's forge token

Before the first converge, because the role refuses to run without it. The token goes from Forgejo straight into the secret store and is never printed:

```bash
./run/host-ssh 216 "su - git -c '/usr/local/bin/forgejo --config /etc/forgejo/app.ini \
  admin user generate-access-token \
  --username matabot \
  --token-name workstation \
  --scopes write:repository,write:issue,read:user \
  --raw'" \
| ./run/pve-ssh 'read -r t && printf "export MATABOT_FORGE_TOKEN=%s\n" "$t" > /zpool/secrets/claude_workstation.sh && chmod 0644 /zpool/secrets/claude_workstation.sh'

./run/pve-ssh 'wc -c /zpool/secrets/claude_workstation.sh'
# 68 /zpool/secrets/claude_workstation.sh
```

`read:user` is for `fj whoami` and nothing else. Mode `0644` is required, not careless: the runner is unprivileged and cannot read a `0600` secret.

### 2. Apply

Dispatch the `_vm.yml` workflow for `218 - workstation`, then `_dns.yml` with `apply`. From a runner shell the equivalent is:

```bash
./run/execute_runner terraform_vm 218 apply
./run/execute_runner ansible_vm 218
./run/execute_runner terraform_dns apply
```

A freshly created VM does not trust the laptop yet; run `./run/host-key-push 218` once before using `./run/host-ssh 218`.

### 3. Log Claude Code in

The subscription login is interactive, so it is done once by hand, as the agent:

```bash
./run/host-ssh 218
su - agent
claude
# /login → Claude account with subscription → open the URL, paste the code back
```

Still in that session, confirm the managed settings are in force:

- `/status` lists **Enterprise managed settings (file)** among the setting sources.
- `/mcp` shows no claude.ai connectors (no Gmail, Drive or Calendar).
- `/permissions` shows the managed allow and deny lists and no way to add a rule.
- Shift+Tab never offers bypass permissions mode.

Then, from the agent's shell:

```bash
fj -H http://forge.home.matagoth.com:3000 whoami
# currently signed in to matabot@forge.home.matagoth.com:3000
```

And as root, after running any Bash command in a session:

```bash
journalctl -t claude-code-audit -n 5
# ... claude-code-audit[...]: {"session_id":"…","cwd":"/home/agent/work/…","command":"git status"}
```

### 4. Grant repositories

The bot sees nothing until it is granted a repository through the `agents` team. The procedure and the checks a repository must pass first are under [Forgejo](#forgejo). Clone granted repositories under `/home/agent/work`. The agent reaches the forge on its own address, not through the reverse proxy, but git rewrites the public URL, so the clone URL from the web UI works as it is:

```bash
git clone https://forge.homelab.matagoth.com/matagoth-zaibatsu/<repo>.git ~/work/<repo>
git -C ~/work/<repo> remote get-url origin
# https://forge.homelab.matagoth.com/matagoth-zaibatsu/<repo>.git  (fetched via http://forge.home.matagoth.com:3000/)
```

### 5. The egress fence

The role enforces from the first converge: squid lets the agent reach only the names in `claude_workstation_egress_allowlist`, and the firewall closes every other way out. The converge ends by checking that squid refuses a name off the list, so a green run means squid enforces. That a program going round the proxy is dropped is a separate check, a direct request as the agent that must time out:

```bash
./run/host-ssh 218 'runuser -u agent -- curl -sS --noproxy "*" --max-time 5 -o /dev/null https://1.1.1.1/ ; echo exit=$?'
# curl: (28) Connection timed out after 5000 milliseconds
# exit=28
```

What is being refused:

```bash
./run/host-ssh 218 'grep TCP_DENIED /var/log/squid/access.log | tail'

# Traffic that tried to go round the proxy, out and in
./run/host-ssh 218 'nft list set inet egress observed_output; nft list set inet ingress observed_input'
```

A `TCP_TUNNEL/503 ... HIER_NONE` line is not a refusal: squid is holding a failed DNS lookup (the resolver has answered `SERVFAIL` for `astral.sh` more than once). Retry a minute later.

To widen the list for a new kind of work, build it from a record rather than a guess. Set `claude_workstation_egress_enforce: false` on a branch and dispatch `_vm.yml` from it; squid then allows every name and logs it. Run the work as the agent in a throwaway home, so its tool installs start from nothing and its own home is left alone. This is how the current list was built, from Claude Code's, uv's, mise's and mait-code's installers, a mise/uv/npm project and a first memory search:

```bash
./run/host-ssh 218
date -u +%s > /var/tmp/record-start
install -d -o agent -g agent -m 0700 /var/tmp/record-home
runuser -u agent -- env HOME=/var/tmp/record-home \
  HTTP_PROXY=http://127.0.0.1:3128 HTTPS_PROXY=http://127.0.0.1:3128 \
  http_proxy=http://127.0.0.1:3128 https_proxy=http://127.0.0.1:3128 \
  NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 \
  PATH=/var/tmp/record-home/.local/bin:/usr/local/bin:/usr/bin:/bin \
  bash -l
# ... run the installers or the workflow, then exit

awk -v s="$(cat /var/tmp/record-start)" '$1 >= s {print $4, $6, $7}' /var/log/squid/access.log \
  | sed -E 's#(https?://[^/]+).*#\1#' | sort | uniq -c | sort -rn
rm -rf /var/tmp/record-home /var/tmp/record-start
```

Add the names the work needs to `claude_workstation_egress_allowlist`, set enforcement back on, and dispatch again. Squid keeps two days of logs, so read the record the same day.

### 6. Run a Remote Control server

A project gets a Remote Control server when its `claude-rc@` unit runs. Projects listed in `claude_workstation_rc_projects` start at boot. Until maitre-d's UI exists, start any other one as root:

```bash
./run/host-ssh 218 'systemctl start claude-rc@<project>; sleep 10; systemctl is-active claude-rc@<project>'
# active
```

It then appears in the Claude app and at claude.ai/code under the project's name. The first start in a folder marks it trusted, so there is no prompt to answer. To see what the server is showing, or to use the session by hand:

```bash
./run/host-ssh 218
su - agent
tmux -L <project> attach      # Ctrl-b d to leave it running
```

Stop it with `systemctl stop claude-rc@<project>`, which ends every session it started. A unit that is **failed** has restarted five times in fifteen minutes. The usual cause is an expired login (step 3):

```bash
./run/host-ssh 218 'systemctl status claude-rc@<project> --no-pager; journalctl -u claude-rc@<project> -n 20 --no-pager'
```

### 7. maitre-d

The `maitre_d` role installs the control service from the pinned release, fetched with `forge-deploy`'s read-only token (see [Forgejo](#forgejo) for the `deploy` team and minting it into `/zpool/secrets/maitre_d.sh`). Two things it cannot do: set the web UI's password, and mint the MCP clients' tokens. Both run as the `maitre-d` user and read secrets from stdin or print them once, never from the command line, because the agent can read every process's arguments.

**Set the web UI password.** Until it is set, every login fails. Setting it again ends every session:

```bash
./run/host-ssh 218
runuser -u maitre-d -- /opt/maitre-d/venv/bin/maitred password set --config /etc/maitre-d/maitred.toml
# prompts twice
```

Then sign in at `https://maitre-d.homelab.matagoth.com` from the laptop or the desktop. Every other address gets a `403` from the proxy.

**Mint a token per MCP client.** The client name is what the board records as the author of cards that client creates or refines, so give each machine or agent its own. The proxy lets only the laptop and the desktop through, `/mcp` included, so another client (Hermes, say) also needs its address in the catalogue entry's `allow`:

The token is shown once, on stdout; the token's row goes to stderr. On the laptop, send it straight into a file of its own, so it never reaches the terminal, the shell history or Claude Code's config:

```bash
umask 077 && mkdir -p ~/.config/maitre-d
./run/host-ssh 218 'runuser -u maitre-d -- /opt/maitre-d/venv/bin/maitred token mint laptop -s card:create -s card:refine --config /etc/maitre-d/maitred.toml' \
  > ~/.config/maitre-d/laptop.token
#    1  laptop   read card:create card:refine   created 2026-10-13T14:50:25+00:00  last used never  live

stat -c '%A %s' ~/.config/maitre-d/laptop.token
# -rw------- 48
```

Add maitre-d at user scope, with a `headersHelper` that reads the file each time Claude Code connects. Passing the token with `--header` would leave it in the shell history and in plain text in `~/.claude.json`:

```bash
claude mcp add-json -s user maitre-d '{"type":"http","url":"https://maitre-d.homelab.matagoth.com/mcp","headersHelper":"printf '"'"'{\"Authorization\":\"Bearer %s\"}'"'"' \"$(cat ~/.config/maitre-d/laptop.token)\""}'

claude mcp list | grep maitre-d
# maitre-d: https://maitre-d.homelab.matagoth.com/mcp (HTTP) - ✔ Connected
```

A session already running does not pick the server up; start a new one. It then has the `rmc_` tools (`rmc_list_cards`, `rmc_create_card`, `rmc_refine_card` and the other reads). A card created or refined from it shows `created_by: laptop`, and the refine adds a comment by `laptop`. The remote API cannot archive or delete, so a test card is archived on 218 as the agent:

```bash
./run/host-ssh 218 'runuser -l agent -c "mc-tool-board archive <card-id>"'
# Card #<card-id> → Archived.
```

**Rotate a client's token.** Mint a new one into the same file, reconnect, then revoke the old one by its id. Revocation takes effect on the client's next request:

```bash
./run/host-ssh 218 'runuser -u maitre-d -- /opt/maitre-d/venv/bin/maitred token mint laptop -s card:create -s card:refine --config /etc/maitre-d/maitred.toml' \
  > ~/.config/maitre-d/laptop.token
# in Claude Code: /mcp → maitre-d → Reconnect (or start a new session)

./run/host-ssh 218 'runuser -u maitre-d -- /opt/maitre-d/venv/bin/maitred token list --config /etc/maitre-d/maitred.toml'
#    1  laptop   read card:create card:refine   created …  last used …  live
#    2  laptop   read card:create card:refine   created …  last used …  live
./run/host-ssh 218 'runuser -u maitre-d -- /opt/maitre-d/venv/bin/maitred token revoke <old-id> --config /etc/maitre-d/maitred.toml'
```

If a token may have leaked, revoke it first and mint second; the client is down until the new file is in place.

**Check it.** `/healthz` is unauthenticated. `memory_search` should be `hybrid`; anything else comes with `memory_search_reason` (maitre-d's README lists them):

```bash
curl -s https://maitre-d.homelab.matagoth.com/healthz
# {"status":"ok","version":"0.5.0","memory_search":"hybrid","memory_search_reason":null}

# The agent is refused the port outright, and the proxy is its only way in
./run/host-ssh 218 'runuser -u agent -- curl -s --max-time 5 http://10.20.1.218:8790/healthz; echo exit=$?'
# exit=7
```

### 8. Run a test job

`claude-job@` runs maitre-d's workflow runner, installed by the `maitre_d` role into `/opt/maitre-d-runner` from the pinned release. Until maitre-d's scheduler writes jobs itself, a job is started by hand: write its directory as `maitre-d`, then start the unit. Do this after the first converge and after every maitre-d bump, since a bump can move the Claude Code that jobs run.

Check the install first. Nothing under the runner's directory may be the agent's to change, and the bundled CLI is the one the release notes name:

```bash
./run/host-ssh 218 'find /opt/maitre-d-runner ! -type l \( ! -user root -o -perm /022 \) -print | wc -l'
# 0
./run/host-ssh 218 'cd / && runuser -u agent -- /opt/maitre-d-runner/venv/lib/python3*/site-packages/claude_agent_sdk/_bundled/claude --version'
# 2.1.300 (Claude Code)
```

Pick a forge-native checkout under `~agent/work` with a clean tree and an `origin`, then make a test card in it as the agent. The `default` workflow does the card, commits on a `card/<id>-<slug>` branch, pushes the branch (no PR) and completes the card:

```bash
./run/host-ssh 218
project=<project>
card=$(runuser -l agent -c "cd ~/work/$project && mc-tool-board add 'Job smoke: add GREETING.md' --project $project --json" | jq .id)
runuser -l agent -c "cd ~/work/$project && mc-tool-board refine $card --description 'Add a file named GREETING.md at the repository root that says hello.' --acceptance '- [ ] GREETING.md exists at the repository root and contains the word hello.'"
```

Write the job's directory as `maitre-d`. `input.json` is a `RunInput` from maitre-d's contract, built from the card as the board holds it:

```bash
job=smoke-$card
install -d -o maitre-d -g maitre-d -m 0700 /var/lib/maitre-d/jobs/$job
printf 'CLAUDE_JOB_PROJECT=%s\n' "$project" \
  | runuser -u maitre-d -- tee /var/lib/maitre-d/jobs/$job/job.env > /dev/null
runuser -l agent -c "cd ~/work/$project && mc-tool-board show $card --json" \
  | jq -c '{workflow: "default", on_limit: "fail",
            card: {id, project, title, description: (.description // ""), acceptance_criteria: (.acceptance_criteria // "")}}' \
  | runuser -u maitre-d -- tee /var/lib/maitre-d/jobs/$job/input.json > /dev/null

systemctl start claude-job@$job
journalctl -fu claude-job@$job
# INFO maitre_d_runner: card #<card>: default workflow
# …
# INFO maitre_d_runner: card #<card>: done
```

Read the outcome. It must parse as the contract, and say `done` with no denials. Each stage is a session of its own, and the telemetry mod records each one as `kind: job` against the unit:

```bash
/opt/maitre-d-runner/venv/bin/python -c 'import sys; from maitre_d_contract import parse_outcome; o = parse_outcome(open(sys.argv[1], "rb").read()); print(o.outcome, len(o.stages), "steps", len(o.denials), "denials")' \
  /var/lib/maitre-d/jobs/$job/result.json
# done <n> steps 0 denials
jq -r '.stages[] | [.name, .status, (.cost_usd // "")] | @tsv' /var/lib/maitre-d/jobs/$job/result.json

jq -r "select(.unit == \"claude-job@$job.service\") | [.kind, .claude_version, .updated_at] | @tsv" /var/lib/claude-telemetry/*.json
# job  2.1.300  …   (one line per model stage)

runuser -l agent -c "cd ~/work/$project && mc-tool-board show $card | head -2"
# #<card> (medium) Job smoke: add GREETING.md
#   project: <project>   status: Done
```

`parse_outcome` failing, or a `result.json` that is empty, means the runner wrote nothing usable: the journal has why. Exit status 2 with an empty result is an invalid `input.json`.

Clean up: delete the pushed branch, put the checkout back on its default branch, archive the card, and clear and remove the job:

```bash
runuser -l agent -c "cd ~/work/$project && b=\$(git branch --show-current) && git switch -q - && git push -q origin --delete \$b && git branch -q -D \$b"
runuser -l agent -c "mc-tool-board archive $card"
systemctl reset-failed claude-job@$job 2> /dev/null || true
rm -r /var/lib/maitre-d/jobs/$job
```

**Bumping maitre-d.** A release pins both maitred and the runner, and through `claude-agent-sdk` the Claude Code that jobs run. Set `maitre_d_version` and `maitre_d_commit` in `ansible/roles/maitre_d/defaults/main.yaml` to the new tag and its commit, check the release notes for a new mait-code pin (move `claude_workstation_mait_code_ref` in the same change) or a new bundled CLI, and converge 218: dispatch `_vm.yml` for `218 - workstation`, or `./run/execute_runner ansible_vm 218` from a runner shell. The converge reinstalls whichever of maitred and the runner reports another version. Then run the checks in [Check it](#7-maitre-d) and this test job again.

## ariel

### What the service is

An LXC (219) running ariel and its SearXNG, configured by the `ariel` role: the workstation agents' way to read the web, by id rather than URL, with pages read by a quarantine model. The role README covers the fences and the release mechanism.

Three things the role cannot do, all before the first converge, which refuses to run without them: grant `forge-deploy` the repository, set up the quarantine model and its key in LiteLLM, and write `/zpool/secrets/ariel.sh`.

### 1. Grant `forge-deploy` the repository

The release is cloned on the apply runner with `forge-deploy`'s token, so `ariel` must be one of the `deploy` team's repositories (see [Forgejo](#forgejo) for the team). Find the team's id, then add the repository:

```bash
./run/host-ssh 216 python3 - <<'EOF'
import sqlite3
c = sqlite3.connect('file:/mnt/forgejo/data/forgejo.db?mode=ro', uri=True)
print(c.execute("select id from team where lower_name = 'deploy'").fetchone())
EOF

curl -X PUT \
  -H "Authorization: token <matagoth-token>" \
  https://forge.homelab.matagoth.com/api/v1/teams/<deploy-team-id>/repos/matagoth-zaibatsu/ariel
```

Run the database query from the Forgejo section again to confirm: `repos` should now list `ariel` beside `maitre-d`.

### 2. The quarantine model and its key in LiteLLM

ariel calls the model `ariel-quarantine`, and its key may call nothing else. LiteLLM keeps both in its database, so they are set up in its UI (`https://litellm.homelab.matagoth.com`):

- **Models → Add Model:** provider OpenRouter; under the LiteLLM model name, the custom option, `openrouter/anthropic/claude-haiku-5.5`; public model name `ariel-quarantine`; the existing OpenRouter credential. The key editor only offers models listed in `/v1/models`, and a model reached only through the `openrouter/*` wildcard is not listed, hence the explicit entry.
- **Virtual Keys → Create Key:** models `ariel-quarantine` only, a max budget of `15` with a monthly reset, and LLM API routes only. Copy the key once; it is not shown again.

Check the restriction with the key at hand (`read -s` keeps it out of the shell history and the screen):

```bash
read -rs -p 'LiteLLM key: ' k; echo
for m in ariel-quarantine openrouter/anthropic/claude-opus-5.5; do
  printf '%s: ' "$m"
  curl -sS -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $k" -H 'Content-Type: application/json' \
    https://litellm.homelab.matagoth.com/v1/chat/completions \
    -d "{\"model\":\"$m\",\"max_tokens\":5,\"messages\":[{\"role\":\"user\",\"content\":\"Say ok\"}]}"
done
# ariel-quarantine: 200
# openrouter/anthropic/claude-opus-5.5: 403
```

### 3. Write the secrets

Three values in one file, none of them printed: `forge-deploy`'s token, minted straight from Forgejo; SearXNG's secret, generated on PVE; and the LiteLLM key from step 2, typed at the prompt (in the same shell as step 2, `$k` still holds it).

```bash
./run/host-ssh 216 "su - git -c '/usr/local/bin/forgejo --config /etc/forgejo/app.ini \
  admin user generate-access-token \
  --username forge-deploy \
  --token-name runner-ariel \
  --scopes read:repository \
  --raw'" \
| ./run/pve-ssh 'read -r t && printf "export ARIEL_FORGE_TOKEN=%s\n" "$t" > /zpool/secrets/ariel.sh && chmod 0644 /zpool/secrets/ariel.sh'

./run/pve-ssh 'printf "export ARIEL_SEARXNG_SECRET=%s\n" "$(openssl rand -hex 32)" >> /zpool/secrets/ariel.sh'

[ -n "$k" ] || read -rs -p 'LiteLLM key: ' k; echo
printf '%s\n' "$k" | ./run/pve-ssh 'read -r k && printf "export ARIEL_LITELLM_KEY=%s\n" "$k" >> /zpool/secrets/ariel.sh'
unset k

./run/pve-ssh 'cut -d= -f1 /zpool/secrets/ariel.sh; stat -c %a /zpool/secrets/ariel.sh'
# export ARIEL_FORGE_TOKEN
# export ARIEL_SEARXNG_SECRET
# export ARIEL_LITELLM_KEY
# 644
```

Mode `0644`, as for every secret here: the runner is unprivileged. To replace the LiteLLM key alone, rewrite that line with `sed -i '/^export ARIEL_LITELLM_KEY=/d'` first, then append as above.

### 4. Apply

Dispatch the `_lxc.yml` workflow for `219 - ariel`, then `_dns.yml` with `apply`, then `_lxc.yml` for `210 - prometheus` (the scrape jobs and the dashboard). From a runner shell:

```bash
./run/execute_runner terraform_lxc 219 apply
./run/execute_runner ansible_lxc 219
./run/execute_runner terraform_dns apply
./run/execute_runner ansible_lxc 210
```

The first converge builds the image, which takes a few minutes. It ends by waiting for `/healthz` to report the pinned version.

### 5. Confirm it

From the workstation, the MCP endpoint answers; from anywhere else, nothing does:

```bash
./run/host-ssh 218 'curl -sS --noproxy "*" http://10.20.1.219:8792/healthz'
# {"status":"ok","version":"0.2.0"}

curl -sS --max-time 5 http://10.20.1.219:8792/healthz ; echo exit=$?
# curl: (28) Connection timed out after 5000 milliseconds
# exit=28
```

The first of those needs 218's own fence to allow it, which is the workstation's card, not this one. Until then, check from 219 itself (`./run/host-ssh 219 'curl -sS http://127.0.0.1:8792/healthz'`).

squid serves the open web and refuses the LAN, LiteLLM aside:

```bash
./run/host-ssh 219 'for u in https://example.com/ http://10.20.1.216:3000/ https://litellm.homelab.matagoth.com/health/liveliness; do
  printf "%s: " "$u"; curl -sS -o /dev/null -w "%{http_code}\n" --proxy http://127.0.0.1:3128 --max-time 10 "$u"; done'
# https://example.com/: 200
# http://10.20.1.216:3000/: 403
# https://litellm.homelab.matagoth.com/health/liveliness: 200
```

What was refused inbound, by source:

```bash
./run/host-ssh 219 'nft list set inet ingress observed_input'
```

Prometheus shows both targets up (`up{job=~"ariel|ariel_node"}`), and the `ariel (219)` dashboard is in Grafana.

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
