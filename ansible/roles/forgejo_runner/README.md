# forgejo_runner

Installs the Forgejo Actions runner as a native binary with a systemd unit, and points it at the homelab Forgejo instance. Requires the `docker` role on the same container: every job runs in a container the daemon creates.

This role provisions a **CI runner**. It is not the same kind of machine as the GitHub Actions runner that applies this repository — see [what it can reach](#what-the-runner-can-and-cannot-reach) below, and [create-runner](../../../docs/runbooks/create-runner.md) for the distinction.

## What lives where

| Path | Contents |
|------|----------|
| `/usr/local/bin/forgejo-runner` | The runner binary, version pinned via `forgejo_runner_version` |
| `/etc/forgejo-runner/config.yml` | Configuration, templated from `config.yml.j2`. Contains the connection token, so it is `0640` and owned by `root:runner` |
| `/var/lib/forgejo-runner/` | The runner's home: job working directories and the action cache |

## What the runner can and cannot reach

**It carries no `/pve/secrets` or `/pve/terraform` mounts.** This is the whole point of the container: a machine that runs whatever a workflow says to run must not also hold the credentials and state that apply changes to the homelab. Adding those mounts turns it into an apply-capable machine wearing a CI hat.

It can reach the Forgejo instance, the internet (to pull job images and to fetch actions from `DEFAULT_ACTIONS_URL`), and anything else routable on the homelab subnet — a workflow is arbitrary code, so treat "on the homelab network" as its true blast radius.

Two settings narrow what a *job* can do beyond that, and both are deliberate:

- `container.valid_volumes: []` — a job cannot bind-mount any host path into its container.
- `container.docker_host: "-"` — a job is handed no Docker socket, so it cannot reach the daemon that created it. Workflows that need to build images will not work until this is revisited, and revisiting it means accepting that a job can escape to the host.

The runner is registered instance-level, so **every repository on the forge can run jobs on it**. That is acceptable while every forge repository belongs to the codeowner; it stops being acceptable the moment the forge hosts someone else's code.

## Credentials

The runner authenticates with a UUID and a 40-character hexadecimal shared secret, both exported from `/pve/secrets/forgejo.sh` on the apply runner:

```bash
export FORGEJO_RUNNER_SECRET='<40 hex characters>'
export FORGEJO_RUNNER_UUID='<uuid printed by the register command>'
```

They are minted once, by hand, and recorded there — the same shape as the `MOSQUITTO_HASH_*` secrets. The `forgejo` role re-asserts the registration on every converge using the same secret, which is idempotent: Forgejo derives the UUID from the secret's first 16 bytes, so the same secret always yields the same runner. [create-runner](../../../docs/runbooks/create-runner.md) has the commands.

If either variable is missing the role fails on its first task rather than templating an empty credential, which would otherwise present as a runner that starts cleanly and never appears online.

## Labels

`forgejo_runner_labels` maps a `runs-on` value to the image the job runs in, as `<label>:docker://<image>`. Both defaults resolve to a Node image because most actions — `actions/checkout` among them — are Node programs and fail immediately in an image without it.

`ubuntu-latest` is present so workflows written against GitHub's runners have somewhere to land. It is a Node image, not an Ubuntu runner image, and does not carry the toolchain GitHub provides; a workflow that assumes otherwise has to install what it needs.

Images are pinned by tag rather than by digest. Note that the runner does the equivalent of `docker run`, so **an image is never re-pulled once present** — moving a tag has no effect on this host until the image is removed by hand.

## Upgrading

Bump `forgejo_runner_version` in `defaults/main.yaml` and re-run `ansible_lxc 501`. The handler restarts the daemon; a job in flight at that moment is lost and has to be re-run.

Check the upstream release notes before crossing a major version — v13 removed the `set-output`, `set-env` and `add-path` workflow commands and raised the minimum Docker version to 25.0, and changes of that shape break workflows rather than the runner.
