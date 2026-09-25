# Create a runner

Runners come in two kinds, each with a VMID range of its own: `500–599` for CI runners and `600–699` for apply runners.

- **Apply runners** execute this repository's own IaC: Terraform applies, Ansible runs, secret access, state mutation. They are GitHub Actions runners, they carry the `/pve/secrets` and `/pve/terraform` mounts, and they are the only execution surface the homelab has. `500` (`github-worker`) is the current one; it predates the range split and is being replaced by `600`.
- **CI runners** execute workflows belonging to repositories hosted on the homelab Forgejo. They are Forgejo Actions runners, they carry **no** secret or state mounts, and they can apply nothing. `501` (`forge-runner`) and `502` (`forge-runner-2`) are the current ones.

The distinction matters because a runner runs whatever a workflow tells it to. An apply runner is trusted with the credentials that change the homelab; a CI runner must not be, or every repository on the forge inherits that trust. Do not add the secret mounts to a CI runner to make something work — the thing that needs them belongs on an apply runner.

Addresses do not follow the usual `10.20.1.<vmid>` mapping in either range: CI runners take `10.20.5.<vmid - 499>` and apply runners take `10.20.6.<vmid - 599>`. See [reference/lxc-schema](../reference/lxc-schema.md).

CI runners are provisioned the same way as any other service (see [add-service](add-service.md)), with the runner-specific manual steps below. Apply runners are not: `terraform_lxc` and `ansible_lxc` refuse the `600–699` range. An apply runner's own container is where applies run, so provisioning or converging it from a job risks the job destroying or restarting the machine it is running on. Apply runners are created and converged by a bootstrap instead.

## What is in IaC and what is not

A runner's *container* is described like any other LXC: a YAML file at `config/lxc/<vmid>.yaml`, `base` plus its roles, and entries in the cross-cutting layers that apply. A CI runner's YAML is applied by `terraform_lxc` and `ansible_lxc`; an apply runner's is applied by the bootstrap. DNS and the reverse proxy do not apply to either kind — a runner publishes nothing — so the service catalogue has no entry for one either. Monitoring optionally applies.

A runner's *pairing with its forge* is where the two kinds diverge:

- **GitHub** issues a short-lived registration token bound to the human who generated it. Baking that into automation would leak a privileged credential into a system that does not need it, so it stays manual: the bootstrap prompts for a token once.
- **Forgejo** supports offline registration, where you mint the shared secret yourself. That secret lives in `/pve/secrets/` like every other secret and both ends converge to it, so only the initial minting is manual.

---

# Forgejo Actions CI runner

Enabling Actions on the Forgejo instance is a converge of `216` and needs nothing manual. Pairing a runner with it needs the five steps below, of which only the first two are done by hand and only once per runner.

**There is more than one CI runner, and the procedure below is per runner.** `501` was the first; `502` exists so that a sick runner is not a CI outage, since a repository that gates its releases on a green run cannot cut one while the only lane is down. Every step below is written with `<vmid>` where the runner's own VMID goes — substitute it rather than copying `501`'s values, and read [step 1](#1-mint-this-runners-shared-secret-and-register) carefully, because the one way to get this wrong produces a fleet that looks fine and is not.

## 1. Mint this runner's shared secret and register

A runner authenticates with a 40-character hexadecimal secret and a UUID. Forgejo derives the UUID from the secret's first 16 bytes, so registering is idempotent: the same secret always yields the same runner, and the `forgejo` role re-asserts it on every converge.

That derivation cuts both ways. **Each runner needs a secret of its own.** Reusing one runner's secret for another does not produce two runners sharing credentials — it produces the *same* UUID, so the second registration is the first runner under a new name, and jobs go to whichever container happens to poll first. Both containers converge cleanly and the admin list simply comes up one runner short. The `forgejo` role asserts the secrets are distinct so this cannot happen silently, but the assertion only helps if you generate a fresh secret here rather than copying.

Generate the secret on the Forgejo container and register with it, capturing the UUID it prints:

```bash
./run/host-ssh 216

su - git -c '/usr/local/bin/forgejo forgejo-cli actions generate-secret'
# 7c31591e8b67225a116d4a4519ea8e507e08f71f

printf '%s' '<secret>' > /etc/forgejo/runner-secret-forge-runner-<vmid>
chown git:git /etc/forgejo/runner-secret-forge-runner-<vmid>
chmod 0600 /etc/forgejo/runner-secret-forge-runner-<vmid>

su - git -c '/usr/local/bin/forgejo --config /etc/forgejo/app.ini \
  forgejo-cli actions register \
  --name forge-runner-<vmid> \
  --secret-file /etc/forgejo/runner-secret-forge-runner-<vmid> \
  --keep-labels'
# 37633331-3539-3165-3862-363732323561
```

Runners are named after their VMID because that is the only identifier that leads from a runner sitting offline in the admin list back to the container to go and look at. The secret file is named to match; both are re-asserted by the `forgejo` role on the next converge of `216`, so this hand-registration is only needed to get the UUID out of Forgejo before the container exists.

The UUID is printed without a trailing newline, so it runs into the next shell prompt — copy it carefully.

Two flags are load-bearing. `--config` must come **before** `forgejo-cli`; it is a flag on the root command, and placing it after the subcommand is an unknown-flag error. `--keep-labels` prevents the command from resetting the runner's stored labels to a single empty string — the runner declares its own labels in its configuration, and this command should not touch them.

Omitting `--scope` registers a **global** runner: one visible to every repository on the instance. That is the intent here.

## 2. Record both halves in the secret store

`/pve/secrets/` inside a runner is `/zpool/secrets/` on the PVE host. Edit it there:

```bash
./run/pve-ssh

cat >> /zpool/secrets/forgejo.sh <<'EOF'
export FORGEJO_RUNNER_<vmid>_SECRET='<secret>'
export FORGEJO_RUNNER_<vmid>_UUID='<uuid>'
EOF
chmod 0644 /zpool/secrets/forgejo.sh
```

The variables are named after the VMID — `FORGEJO_RUNNER_501_SECRET`, `FORGEJO_RUNNER_502_SECRET` and so on — because a single unsuffixed pair cannot describe more than one runner, and nothing else in the fleet is a stable name for a container.

`0644` is deliberate and every other file in that directory carries it. The runner is an unprivileged container, so these files appear inside it as `nobody:nogroup` whatever they are on the host; the world-read bit is the only thing that lets the runner read them. Written `0600`, the file is silently invisible and the apply fails as though the secret were never set.

Both are read at apply time: the `forgejo` role uses the secret to re-assert the registration on `216`, and the `forgejo_runner` role templates both into the runner's own configuration. If either is missing, the `forgejo_runner` role fails on its first tasks rather than producing a runner that starts cleanly and never comes online.

## 3. Declare the container and the pairing

Two files, and both are needed — a runner container with no entry on `216` is never registered, and an entry on `216` with no container is a permanently offline runner in the admin list.

`config/lxc/<vmid>.yaml` describes the container. It carries `base`, `docker` and `forgejo_runner`, no `/pve` mounts at all, and an address from the CI runner range (`10.20.5.<vmid - 499>` — see [reference/lxc-schema](../reference/lxc-schema.md)). The role is given the names of the variables recorded in step 2:

```yaml
ansible:
  roles:
    - base
    - docker
    - role: forgejo_runner
      vars:
        forgejo_runner_uuid_env: FORGEJO_RUNNER_<vmid>_UUID
        forgejo_runner_secret_env: FORGEJO_RUNNER_<vmid>_SECRET
```

Leave the labels alone. Every runner declares the role defaults, so any job can land on any runner — which is the entire reason there is more than one. A label present on one runner and absent from the others makes the jobs that use it single-lane again.

`config/lxc/216.yaml` pairs it with the forge, by adding an entry to `forgejo_runners`:

```yaml
        forgejo_runners:
          - name: forge-runner-501
            secret_env: FORGEJO_RUNNER_501_SECRET
          - name: forge-runner-<vmid>
            secret_env: FORGEJO_RUNNER_<vmid>_SECRET
```

Add the `_lxc.yml` dropdown and `homelab_iac.yml` matrix entries as for any container. Lint enforces that the dropdown stays 1:1 with `config/lxc/*.yaml`, so a missing entry fails CI; the matrix is not checked, and a runner missing from it is simply never converged by a full apply.

## 4. Provision the container

Normally through the **HomeLab IAC** workflow dispatch, or the per-container **LXC** workflow with the new runner selected. From a shell on an apply runner it is:

```bash
./run/execute_runner terraform_lxc <vmid> apply
./run/execute_runner ansible_lxc <vmid>
```

Converge `216` too, so the `[actions]` configuration and the registration land:

```bash
./run/execute_runner ansible_lxc 216
```

The `forgejo_runner` config template notifies a service restart, so converging a runner kills any job in flight on it. Converge one runner at a time and CI keeps a lane throughout; converge them in parallel and it does not.

## 5. Confirm it is online

The runners appear under **Site Administration → Actions → Runners** at `https://forge.homelab.matagoth.com/-/admin/actions/runners`, each named for its VMID, with a green **Idle** status and the labels it declared.

Check the **count and the UUIDs**, not just that the new one is green. A runner registered with a secret that another runner already uses does not show up as an error — it shows up as one fewer row than expected, because Forgejo has been told about the same runner twice. Two rows with two distinct UUIDs is the thing being confirmed.

The admin list is the quick look, but it does not show UUIDs, so the registrations themselves are read from Forgejo's database. `216` has no `sqlite3` binary and should not grow one for this; its Python does the job, opened read-only so a mistyped query cannot touch a live instance:

```bash
./run/host-ssh 216 'python3 -c "
import sqlite3
c = sqlite3.connect(\"file:/mnt/forgejo/data/forgejo.db?mode=ro\", uri=True)
for r in c.execute(\"select id, uuid, name, owner_id, repo_id, agent_labels from action_runner order by id\"):
    print(r)
"'
# (1, '63323135-...', 'forge-runner-501', 0, 0, '["docker","ubuntu-latest"]')
# (2, '37656137-...', 'forge-runner-502', 0, 0, '["docker","ubuntu-latest"]')
```

One row per runner, each UUID different, and `owner_id`/`repo_id` both `0` — that pair being zero is what makes a runner instance-level rather than scoped to one repository or organisation.

If a runner does not appear, its own daemon log says why:

```bash
./run/host-ssh <vmid> 'journalctl -u forgejo-runner -n 100 --no-pager'
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

A runner is only half of what a workflow needs. The token Forgejo hands each job cannot open a pull request on this instance, so repositories that want one use a shared token from a dedicated account instead — minting it and granting it access is in [post-deploy-setup](post-deploy-setup.md), under Forgejo.

Note that the runner does the equivalent of `docker run`, so **a job image is never re-pulled once present**. Moving a tag upstream has no effect on a runner until the image is removed by hand — on every runner, since a job may land on any of them:

```bash
for vmid in 501 502; do
  ./run/host-ssh "${vmid}" 'docker image rm docker.io/library/node:22-bookworm'
done
```

## Proving a runner can be lost

The point of a second runner is that CI survives losing one, and that is worth testing rather than assuming — the failure mode it guards against (a label only one runner declares, a container that never came back) is invisible until the day it matters.

Stop the daemon on one runner, leave it stopped, and dispatch a workflow that normally runs there:

```bash
./run/host-ssh 501 'systemctl stop forgejo-runner'
```

The stopped runner goes **Offline** in the admin list and the job runs on the other one. If it queues instead of starting, the surviving runner does not declare the label the workflow asks for.

Which runner actually took each job is not on the job record — it is on the task the job was dispatched to, so confirming it takes a join. `status = 1` is success and `6` is running; the enum is not the one the web UI's wording suggests, so read the number rather than guessing:

```bash
./run/host-ssh 216 'python3 -c "
import sqlite3
c = sqlite3.connect(\"file:/mnt/forgejo/data/forgejo.db?mode=ro\", uri=True)
run = c.execute(\"select id from action_run where repo_id=<repo-id> order by id desc limit 1\").fetchone()[0]
for row in c.execute(\"\"\"select j.name, j.status, j.runs_on, r.name
                        from action_run_job j
                        left join action_task t on t.id = j.task_id
                        left join action_runner r on r.id = t.runner_id
                        where j.run_id = ? order by j.id\"\"\", (run,)):
    print(row)
"'
# ('ruff', 1, '["docker"]', 'forge-runner-502')
```

Every job showing the surviving runner's name is the proof; a green run on its own is not, since nothing in the result says where it ran. Start the stopped runner again afterwards:

```bash
./run/host-ssh 501 'systemctl start forgejo-runner'
```

The daemon is enabled, so a reboot would also bring it back — but a runner left stopped is a lane silently missing until something else fails, so put it back deliberately.

## Upgrading the runner software

Bump `forgejo_runner_version` in `ansible/roles/forgejo_runner/defaults/main.yaml` and re-run `ansible_lxc <vmid>` for each runner. The handler restarts the daemon; any job in flight on that runner is lost and has to be re-run. Converge them one at a time so a lane stays up, and check the first is back online before starting the second — a version that fails to start takes out one runner rather than all of them.

## Removing a runner

Delete it from the Forgejo admin runner list, then destroy the container:

```bash
./run/execute_runner terraform_lxc <vmid> destroy
```

Remove `config/lxc/<vmid>.yaml`, its `_lxc.yml` dropdown entry and its `homelab_iac.yml` matrix entry — lint enforces that the dropdown and the config files stay in 1:1 sync, so a half-removal fails CI. Remove its entry from `forgejo_runners` in `config/lxc/216.yaml` so the `forgejo` role stops re-registering a runner that no longer exists, and clear that runner's `FORGEJO_RUNNER_<vmid>_SECRET` and `FORGEJO_RUNNER_<vmid>_UUID` from `/zpool/secrets/forgejo.sh`.

Removing the last CI runner leaves the forge with no way to run a job, which for a repository that gates releases on a green run means no releases. Confirm that is intended.

---

# GitHub Actions apply runner

An apply runner cannot be created the way everything else is, because creating things is its job. The first one has nothing to create it, and a runner creating or converging its own container from a job would be operating on the machine the job runs on. `terraform_lxc` and `ansible_lxc` therefore refuse the `600–699` range, and apply runners are built by `bootstrap/apply-runner` from a laptop instead.

The bootstrap is deliberately small. It creates the container on PVE from `config/lxc/<vmid>.yaml`, copies the repository in, and runs the container's own roles on the container itself with `ansible-playbook -c local`. Everything that makes the container a runner — the user, the SSH key and config, the Actions runner, its registration and service, the toolbox image — is the [`runner` role](../../ansible/roles/runner/README.md). The laptop never holds a secret: the only credential that passes through it is the registration token, and it goes in on stdin.

It all goes through PVE (`pct create`, `pct push`, `pct exec`), so the laptop only needs to reach PVE, which `./run/pve-ssh` already does. The new container does not have to trust the laptop, and homelab DNS does not have to be up.

## Before you start

- **The shared SSH key is in the secrets store.** Every guest trusts one apply-runner key, `config/worker_id_rsa.pub`. Its private half must be at `/zpool/secrets/runner_id_rsa` on PVE, with the `.pub` alongside, both `0644`. The `runner` role refuses to continue without them.

  ```bash
  ./run/pve-ssh 'ls -la /zpool/secrets/runner_id_rsa*; ssh-keygen -lf /zpool/secrets/runner_id_rsa.pub'
  # -rw-r--r-- 1 root root 2610 ... /zpool/secrets/runner_id_rsa
  # -rw-r--r-- 1 root root  574 ... /zpool/secrets/runner_id_rsa.pub
  # 3072 SHA256:TpoSkxWUZox8YT2qAP/DqAtOcSDthQIo9/O84ed/yiw runner@github-worker (RSA)
  ```

  The fingerprint must match `ssh-keygen -lf config/worker_id_rsa.pub`.

- **`yq` is on the laptop.** The bootstrap reads the container's YAML with it.
- **Changes are committed.** The bootstrap copies the repository as of `HEAD`, not the working tree.

## 1. Declare the container

`config/lxc/<vmid>.yaml`, in the `600–699` range, addressed `10.20.6.<vmid - 599>`. The schema is the ordinary one, with two differences: the template must be pinned, because the bootstrap does not guess one, and the `/pve` mounts go under `pve_extra`, from where the bootstrap passes them to `pct create`:

```yaml
---
terraform:
  vmid: 600
  hostname: github-runner
  ip_address: 10.20.6.1/16
  nameserver: 10.20.0.1
  cpu_core_count: 4
  memory: 8192
  swap: 1024
  start_on_boot: true
  rootfs_size: 20G
  ostemplate: local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst

pve_extra:
  - mp0: /zpool/secrets,mp=/pve/secrets
  - mp1: /zpool/terraform,mp=/pve/terraform

ansible:
  roles:
    - base
    - docker
    - role: runner
      vars:
        runner_name: github-runner-600
```

The runner is named `github-runner-<vmid>`, the only name that leads from a runner offline in GitHub's list back to a container. There is no `_lxc.yml` dropdown entry and no `homelab_iac.yml` matrix entry: the workflows run through the operations that refuse this range, and lint leaves it out of the dropdown check.

Merge the YAML before creating the runner, so the container that exists is the one `main` describes.

## 2. Create it

Generate a registration token under **Settings → Actions → Runners → New self-hosted runner** on the repository. It is the value after `--token` in the *Configure* snippet, and it expires after an hour, so generate it right before this step. Then:

```bash
bootstrap/apply-runner create <vmid>
# GitHub registration token:
#
# ==> Fetching template debian-13-standard_13.6-1_amd64.tar.zst if PVE lacks it
# ==> Creating container <vmid>
# ==> Waiting for the network
# ==> Pushing the repository at <commit>
# ==> Converging <vmid> locally
# PLAY RECAP ...
# localhost : ok=... changed=... failed=0 ...
#
# ==> Done. <vmid> should now show as Idle under Settings -> Actions -> Runners
```

The token is asked for first, so the rest runs unattended. On a fresh container it takes about ten minutes, most of it building the toolbox image.

The new runner is not yet trusted by the laptop. To reach it with `./run/host-ssh`, push the laptop's key through PVE once:

```bash
./run/host-key-push <vmid>
```

## 3. Confirm it works

In GitHub's runner list, the new runner is **Idle** with the labels `self-hosted, Linux, X64`. On the container:

```bash
./run/host-ssh <vmid> 'systemctl status "actions.runner.*" --no-pager | head -5'
./run/host-ssh <vmid> 'ls /pve/secrets /pve/terraform; docker image ls runner-toolbox'
```

Idle only means registered. It is proven by running real work: dispatch **Build Runner Image**, then an LXC plan and an LXC converge against a quiet container, and a DNS plan. Every workflow is `runs-on: self-hosted`, so while another apply runner is online the job may land on either. To prove a new one specifically, stop the others' runner service for the duration.

If `create` fails at registration — usually an expired token — the container is otherwise complete. Generate a fresh token and finish with `converge`, which asks for one when the runner is not registered:

```bash
bootstrap/apply-runner converge <vmid>
# Not registered yet. GitHub registration token:
```

Any other failure is cheapest to redo from scratch: `./run/pve-ssh 'pct stop <vmid>; pct destroy <vmid> --purge'` and run `create` again. An apply runner keeps nothing of its own; its state and secrets are the PVE bind mounts.

## Converging a runner

An apply runner is converged by the bootstrap too, for the same reason it is created by it: a job converging its own runner can restart Docker or the runner service underneath itself. After changing an apply runner's YAML or any of its roles, merge, then:

```bash
bootstrap/apply-runner converge <vmid>
```

This pushes `HEAD` and re-runs the roles. A registered runner needs no token. The runner service is restarted if the role changes it, so run it while no apply is in flight.

Resizing is not a converge. `cpu_core_count`, `memory` and the rest of `terraform:` only take effect at creation, so change the YAML and either rebuild the runner or apply the same change with `pct set` so the two agree.

## Updating the runner software

The runner updates itself. GitHub stops dispatching to a runner that falls too far behind, so the `runner` role installs `runner_version` on a fresh container and leaves an installed runner's binaries alone. Bump `runner_version` and `runner_checksum` in the role's defaults only to change what a new runner starts from. The checksum is in the release notes, next to `actions-runner-linux-x64-<version>.tar.gz`.

## Removing a runner

1. From GitHub's runner list, remove the runner. It stops accepting new jobs.
2. Wait for any in-flight job to finish.
3. Destroy the container. There is no Terraform state to clean up:

   ```bash
   ./run/pve-ssh 'pct stop <vmid>; pct destroy <vmid> --purge'
   ```

4. Delete `config/lxc/<vmid>.yaml`.

Removing the container before de-registering leaves an orphan entry in GitHub's runner list, which has to be removed by hand. Removing the last apply runner leaves the homelab with nothing that can apply changes except this bootstrap. Confirm that is intended.

## Verifying an apply runner is healthy

An apply runner is healthy when:

- It appears as **Idle** in GitHub's runner list when no job is queued.
- A trivial workflow run completes on it.
- Its mounts are populated and its toolbox image exists.

```bash
# Service status
./run/host-ssh <vmid> 'journalctl -u "actions.runner.*" -n 100 --no-pager'

# Secret and state mounts, and the key the role installed from them
./run/host-ssh <vmid> 'ls -la /pve/secrets/ /pve/terraform/ /home/runner/.ssh/'
```

Anything less means there is a misconfiguration to chase; the [troubleshooting runbook](troubleshooting.md) covers the common causes.
