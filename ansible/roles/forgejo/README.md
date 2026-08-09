# forgejo

Installs Forgejo as a native binary with a SQLite backend and a systemd unit.

## What lives where

| Path | Contents |
|------|----------|
| `/usr/local/bin/forgejo` | The Forgejo binary, version pinned via `forgejo_version` |
| `/etc/forgejo/app.ini` | Configuration, templated from `app.ini.j2` |
| `/etc/forgejo/secret_key`, `internal_token`, `jwt_secret`, `lfs_jwt_secret` | The four instance secrets, generated once on first apply and referenced from `app.ini` by the matching `*_URI` settings |
| `/mnt/forgejo/data/` | Repositories, SQLite database, LFS storage — lives on the bind-mounted `/zpool/forgejo` dataset |
| `/var/log/forgejo/` | Logs |

## Secrets

Ansible owns `app.ini` and rewrites it on every converge, so any secret stored inline is stripped and regenerated each time. Forgejo's four instance secrets are therefore kept in files of their own and referenced from `app.ini` by the `*_URI` settings, which is the mechanism a bare-metal install has for this.

All four are generated once, on first apply, and never regenerated: `SECRET_KEY` encrypts 2FA secrets, stored credentials and Actions secrets, so rotating it discards them.

Two things about that generation are load-bearing. A `*_URI` pointing at a file that does not exist is **fatal** — Forgejo reads the file, it does not create one — so the files must exist before the service starts. And the values come from `forgejo generate secret` rather than from `openssl`, because the formats are not interchangeable: `INTERNAL_TOKEN` is a signed JWT and the two JWT secrets are base64 of 32 raw bytes. `generate secret` does not load `app.ini`, which is what lets the role recover a host whose config already points at files that are missing.

An earlier arrangement set `FORGEJO__*` variables in `/etc/forgejo/secrets.env` and had systemd load it as an `EnvironmentFile`. That never worked. The env-to-ini translation lives in `environment-to-ini`, a helper shipped only in the container image; the string `FORGEJO__` does not appear in the server binary. The practical effect was that Forgejo generated three of its own secrets on each start, wrote them into `app.ini`, and had them stripped again by the next converge — so they rotated on every apply, and `SECRET_KEY` sat at its upstream default throughout. The role now removes that file.

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

## Actions

Actions is enabled through `app.ini`, and `forgejo_actions_default_url` sets where a workflow's `uses:` resolves when it carries no absolute URL. Forgejo does not run jobs itself — that is the [forgejo_runner](../forgejo_runner/README.md) role on `501`.

This role also *registers* that runner, using the shared secret exported as `FORGEJO_RUNNER_SECRET` from `/pve/secrets/forgejo.sh`. Registration is done offline (`forgejo-cli actions register`) rather than through the web UI, because the runner's credentials are templated onto the runner host by its role and a hand-registered pair would be overwritten on the next converge. The command is idempotent — Forgejo derives the runner's UUID from the secret's first 16 bytes, so re-asserting with an unchanged secret is a no-op.

Omitting `FORGEJO_RUNNER_SECRET` skips registration entirely, which is the right behaviour for a Forgejo that has no runner.

### The CI user

The role also creates `forgejo_ci_user` (`forge-ci`), the account whose token workflows use for the things the automatic per-job token cannot do — opening a pull request, chiefly. Creation is guarded on the user table, so the account is made once and left alone afterwards; its password is random and discarded, because nothing signs in as it.

Two things the role does on *every* converge rather than only at creation:

- It clears the must-change-password flag. `admin user change-password` re-arms that flag as a side effect, and an account carrying it answers `403` to every API call with a message about changing the password — which reads like a token-scope problem and is not one.
- It asserts the account is not an admin, and fails the converge if it is. Branch protection exempts admins unless a rule opts in with `apply_to_admins`, so an admin CI user would push straight through the gates its repositories rely on while the API went on reporting those gates as enforced.

The *token* is not in IaC. It is issued by Forgejo, shown once, and installed as an organisation-level Actions secret named `FORGE_CI_TOKEN`. Neither is the organisation that secret hangs off, nor the `ci` team that gives `forge-ci` its repository access — Forgejo has no admin CLI for organisations, so both are made through the API. See [post-deploy-setup](../../../docs/runbooks/post-deploy-setup.md) for all three; the access grant is a separate concern from the token, and a repository outside the organisation gets neither.

## Upgrading

Bump `forgejo_version` in `defaults/main.yaml`. The role downloads the new binary in-place; the handler restarts the service. Forgejo's schema migrations run automatically on start. Check the upstream release notes for breaking changes before bumping across major versions.
