# Create a runner

Runners live in the `500–599` VMID range and come in two kinds. They are provisioned the same way as any other service (see [add-service](add-service.md)), with the runner-specific manual steps below.

- **Apply runners** execute this repository's own IaC: Terraform applies, Ansible runs, secret access, state mutation. They are GitHub Actions runners, they carry the `/pve/secrets` and `/pve/terraform` mounts, and they are the only execution surface the homelab has. `500` (`github-worker`) is the current one.
- **CI runners** execute workflows belonging to repositories hosted on the homelab Forgejo. They are Forgejo Actions runners, they carry **no** secret or state mounts, and they can apply nothing. `501` (`forge-runner`) is the current one.

The distinction matters because a runner runs whatever a workflow tells it to. An apply runner is trusted with the credentials that change the homelab; a CI runner must not be, or every repository on the forge inherits that trust. Do not add the secret mounts to a CI runner to make something work — the thing that needs them belongs on an apply runner.

Addresses do not follow the usual `10.20.1.<vmid>` mapping in this range; runners take `10.20.5.<vmid - 499>`. See [reference/lxc-schema](../reference/lxc-schema.md).

## What is in IaC and what is not

A runner's *container* is provisioned by IaC like any other LXC: a YAML file at `config/lxc/<vmid>.yaml`, `base` plus its roles, and entries in the cross-cutting layers that apply. DNS and the reverse proxy do not apply to either kind — a runner publishes nothing — so the service catalogue has no entry for one either. Monitoring optionally applies.

A runner's *pairing with its forge* is where the two kinds diverge:

- **GitHub** issues a short-lived registration token bound to the human who generated it. Baking that into automation would leak a privileged credential into a system that does not need it, so it stays manual: IaC prepares the container, you paste a token into it once.
- **Forgejo** supports offline registration, where you mint the shared secret yourself. That secret lives in `/pve/secrets/` like every other secret and both ends converge to it, so only the initial minting is manual.

---

# Forgejo Actions CI runner

Enabling Actions on the Forgejo instance is a converge of `216` and needs nothing manual. Pairing a runner with it needs the four steps below, of which only the first two are done by hand and only once.

## 1. Mint the shared secret and register

The runner authenticates with a 40-character hexadecimal secret and a UUID. Forgejo derives the UUID from the secret's first 16 bytes, so registering is idempotent: the same secret always yields the same runner, and the `forgejo` role re-asserts it on every converge.

Generate the secret on the Forgejo container and register with it, capturing the UUID it prints:

```bash
./run/host-ssh 216

su - git -c '/usr/local/bin/forgejo forgejo-cli actions generate-secret'
# 7c31591e8b67225a116d4a4519ea8e507e08f71f

printf '%s' '<secret>' > /etc/forgejo/runner-secret
chown git:git /etc/forgejo/runner-secret
chmod 0600 /etc/forgejo/runner-secret

su - git -c '/usr/local/bin/forgejo --config /etc/forgejo/app.ini \
  forgejo-cli actions register \
  --name homelab-ci \
  --secret-file /etc/forgejo/runner-secret \
  --keep-labels'
# 37633331-3539-3165-3862-363732323561
```

The UUID is printed without a trailing newline, so it runs into the next shell prompt — copy it carefully.

Two flags are load-bearing. `--config` must come **before** `forgejo-cli`; it is a flag on the root command, and placing it after the subcommand is an unknown-flag error. `--keep-labels` prevents the command from resetting the runner's stored labels to a single empty string — the runner declares its own labels in its configuration, and this command should not touch them.

Omitting `--scope` registers a **global** runner: one visible to every repository on the instance. That is the intent here.

## 2. Record both halves in the secret store

`/pve/secrets/` inside a runner is `/zpool/secrets/` on the PVE host. Edit it there:

```bash
./run/pve-ssh

cat >> /zpool/secrets/forgejo.sh <<'EOF'
export FORGEJO_RUNNER_SECRET='<secret>'
export FORGEJO_RUNNER_UUID='<uuid>'
EOF
chmod 0600 /zpool/secrets/forgejo.sh
```

Both are read at apply time: the `forgejo` role uses the secret to re-assert the registration on `216`, and the `forgejo_runner` role templates both into the runner's configuration on `501`. If either is missing, the `forgejo_runner` role fails on its first task rather than producing a runner that starts cleanly and never comes online.

## 3. Provision the container

Normally through the **HomeLab IAC** workflow dispatch, or the per-container **LXC** workflow with `501 - forge-runner` selected. From a shell on an apply runner it is:

```bash
./run/execute_runner terraform_lxc 501 apply
./run/execute_runner ansible_lxc 501
```

Converge `216` too, so the `[actions]` configuration and the registration land:

```bash
./run/execute_runner ansible_lxc 216
```

## 4. Confirm it is online

The runner appears under **Site Administration → Actions → Runners** at `https://forge.homelab.matagoth.com/-/admin/actions/runners`, labelled `homelab-ci`, with a green **Idle** status and the labels it declared.

If it does not, the daemon's own log says why:

```bash
./run/host-ssh 501 'journalctl -u forgejo-runner -n 100 --no-pager'
```

The two failures worth recognising: a `401` on every poll means the UUID and secret in `/etc/forgejo-runner/config.yml` do not match what Forgejo holds — re-run step 1 with the same secret and compare. A DNS or TLS error on `forge.homelab.matagoth.com` means the runner is registered fine but cannot reach the instance through the reverse proxy, which is a networking problem and not a registration one.

## Proving the path end to end

In any repository on the forge, commit `.forgejo/workflows/ci.yml`:

```yaml
on: [push]
jobs:
  smoke:
    runs-on: docker
    steps:
      - run: echo "the runner runs"
```

Push it and watch the **Actions** tab. The first run is slow — the runner pulls the job image before it can start — and subsequent runs reuse it.

Note that the runner does the equivalent of `docker run`, so **a job image is never re-pulled once present**. Moving a tag upstream has no effect on `501` until the image is removed by hand:

```bash
./run/host-ssh 501 'docker image rm docker.io/library/node:22-bookworm'
```

## Upgrading the runner software

Bump `forgejo_runner_version` in `ansible/roles/forgejo_runner/defaults/main.yaml` and re-run `ansible_lxc 501`. The handler restarts the daemon; any job in flight at that moment is lost and has to be re-run.

## Removing the runner

Delete it from the Forgejo admin runner list, then destroy the container and delete its files:

```bash
./run/execute_runner terraform_lxc 501 destroy
```

Remove `config/lxc/501.yaml`, its `_lxc.yml` dropdown entry and its `homelab_iac.yml` matrix entry — lint enforces that the dropdown and the config files stay in 1:1 sync, so a half-removal fails CI. Clear `FORGEJO_RUNNER_SECRET` and `FORGEJO_RUNNER_UUID` from `/zpool/secrets/forgejo.sh` so the `forgejo` role stops re-registering a runner that no longer exists.

---

# GitHub Actions apply runner

One apply runner suffices for routine workload. Reasons to add a second include:

- **Self-update.** The same runner cannot apply changes that take itself offline (image rebuild, reboot, kernel update). A second runner unblocks those operations.
- **Capacity.** Concurrent jobs queue if there is only one runner. A second runner reduces that queue when applies overlap.
- **Isolation.** Some workloads benefit from running on a runner that does not share state with the production runner.

If none of these applies, do not add one.

## 1. Provision the container

Add `config/lxc/<vmid>.yaml` for the new VMID, declaring the container with the resources it needs and listing the runner role under `ansible:`. An apply runner needs the persistent mounts that make it apply-capable: `/pve/secrets/` and `/pve/terraform/` from the host, plus the runner's `~/.ssh`. Without them it can do nothing useful.

The mount points, applied via `pve_extra:` so they are bind-mounts of the host paths rather than allocated volumes:

```yaml
pve_extra:
  - mp0: /zpool/secrets,mp=/pve/secrets
  - mp1: /zpool/terraform,mp=/pve/terraform
```

Run `terraform_lxc <vmid> apply` followed by `ansible_lxc <vmid>` through `./run/execute_runner` from an existing runner. After this phase, the container exists, has the toolchain installed, and can build the toolbox image, but does not yet appear in GitHub as an available runner.

## 2. Register with GitHub

Generate a one-time runner registration token from GitHub's repository settings (**Settings → Actions → Runners → New self-hosted runner**). Tokens expire quickly; generate the token immediately before this step, not in advance.

In a shell on the new runner container, run the GitHub installer with the token:

```bash
# Setup
GH_RUNNER_VERSION=2.322.0
read -p 'Input GitHub Actions Runner Token: ' GH_RUNNER_TOKEN

# Create folder and download runner
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -O -L "https://github.com/actions/runner/releases/download/v${GH_RUNNER_VERSION}/actions-runner-linux-x64-${GH_RUNNER_VERSION}.tar.gz"
tar xzf "./actions-runner-linux-x64-${GH_RUNNER_VERSION}.tar.gz"
./bin/installdependencies.sh

# Configure and install as a service
RUNNER_ALLOW_RUNASROOT=1 ./config.sh \
  --url https://github.com/wiktordepina/homelab \
  --token "${GH_RUNNER_TOKEN}"
./svc.sh install root
./svc.sh start
```

The registration writes a configuration file inside the container and installs a systemd service that starts on boot.

After registration, the runner appears in GitHub's runner list. Note that the registration is per-runner-instance: destroying the container removes the runner from GitHub on the next housekeeping pass, but a clean removal involves de-registering before destroying. See "Removing a runner" below.

## 3. Build the toolbox image

The runner cannot apply anything until it has the toolbox image. `./run/lint` builds it on first run; alternatively, build it explicitly:

```bash
cd /build  # Wherever the repo is cloned on the runner
git clone https://github.com/wiktordepina/homelab.git  # If not already present
cd homelab/runner-toolbox
docker build -t runner-toolbox .
```

Subsequent applies reuse the existing image until the `runner-toolbox/` sources change.

After this phase, the runner is ready to pick up jobs.

## Updating the runner software

The runner software is installed inside the container by the runner role. Updating to a new version is a configuration change: bump the version pinned by the role, then re-run `ansible_lxc <vmid>`. The role handles stopping the service, swapping the binaries, and starting the service again.

If you ever need to update by hand on the container (for an out-of-band fix only — drift is undesirable):

```bash
cd ~/actions-runner
./svc.sh stop

GH_RUNNER_VERSION=<new-version>
curl -O -L "https://github.com/actions/runner/releases/download/v${GH_RUNNER_VERSION}/actions-runner-linux-x64-${GH_RUNNER_VERSION}.tar.gz"
tar xzf "./actions-runner-linux-x64-${GH_RUNNER_VERSION}.tar.gz"

./svc.sh start
```

Manual updates produce drift that the next configuration apply will partially undo and partially leave alone, in confusing combinations. Prefer the role.

## Removing a runner

Reverse the steps:

1. From GitHub's runner list, remove the runner. This is a graceful de-registration; the runner stops accepting new jobs.
2. Wait for any in-flight job to finish.
3. Run `terraform_lxc <vmid> destroy` to remove the container, and delete `config/lxc/<vmid>.yaml`.

Removing the container before de-registering leaves an orphan entry in GitHub's runner list, which has to be cleaned up by hand.

## Verifying an apply runner is healthy

An apply runner is healthy when:

- It appears as **idle** in GitHub's runner list when no job is queued.
- A trivial workflow run (a no-op job dispatched manually) completes on it.
- `./run/lint` completes locally on the runner, confirming the toolbox image builds and runs.

Useful diagnostic commands on the runner container:

```bash
# Service status
journalctl -u 'actions.runner.*' -n 100

# Confirm secret/state mounts are populated
ls -la /pve/secrets/
ls -la /pve/terraform/
```

Anything less means there is a misconfiguration to chase; the [troubleshooting runbook](troubleshooting.md) covers the common causes.
