# Runner toolbox

The runner toolbox is the container image that holds every tool the homelab needs to apply changes. It is built on the runner from the `runner-toolbox/` sources in this repository and never published to a registry. This document describes what the toolbox provides and how it is invoked. For the reasoning behind the model, see [concepts/runner-model](../concepts/runner-model.md).

## What the image contains

The toolbox bundles, conceptually:

- **Terraform** with a custom Proxmox provider built into the image (sourced from `runner-toolbox/provider/`), so applies do not depend on registry availability for the provider plugin.
- **Ansible** with the collections the homelab's roles depend on.
- **Linting tools** for YAML, Ansible, and Terraform, plus a playbook syntax checker.
- **General utilities** — shell, JSON and YAML processors, networking and SSH clients, version control — that the wrapper scripts rely on.
- **The wrapper scripts themselves** under `runner-toolbox/scripts/` (see below), copied in at image build time.

Versions are pinned at build time and not part of this document; they live next to the image's build inputs (`runner-toolbox/Dockerfile`, `runner-toolbox/pyproject.toml`) and are updated there.

## What the runtime expects

When the toolbox is invoked on the runner, it expects three things to be mounted into it:

- **`/pve/secrets/`** on the host, sourced for environment variables before any tool runs.
- **`/pve/terraform/`** on the host, used as the persistent home for state files.
- **An SSH key directory** (the runner's `~/.ssh`), used by Ansible to reach configured containers.

The repository's working tree is also mounted in at `/build`, since wrapper scripts read configuration from it and Terraform reads its own definitions from it.

If any of these mounts is missing or empty, operations fail in characteristic ways: missing secrets produce authentication errors, missing state files cause Terraform to plan as if everything were new, missing SSH keys cause Ansible to be unable to connect.

## How to invoke it

`./run/execute_runner` is the documented entry point. It takes the name of a control-plane operation (one of the wrapper scripts under `runner-toolbox/scripts/`) and any arguments the operation needs, sets up the mounts and environment, and runs the toolbox image. Do not invoke `docker` directly; `./run/execute_runner` is the API.

Invoking `./run/execute_runner` from a developer machine is unsupported by design — the secrets and state mounts only exist on the runner. A laptop has the wrapper, but using it produces immediate errors because the inputs it depends on are not present. The codeowner intends this — see [concepts/runner-model](../concepts/runner-model.md).

## The control-plane operations

`./run/execute_runner` exposes a small set of operations, each corresponding to a single concern. They are independent; you run them in the appropriate order for the task at hand.

**Per-LXC provisioning** (`terraform_lxc <vmid> <plan|apply|destroy>`). Plan or apply the Terraform configuration under `terraform/lxc/` that creates and shapes one container, identified by VMID. The plan action is read-only and is the right way to preview changes; apply mutates Proxmox.

**Per-LXC configuration** (`ansible_lxc <vmid>`). Run the Ansible roles declared in `config/lxc/<vmid>.yaml`, in order. This assumes the container already exists and is reachable.

**Per-external-host configuration** (`ansible_external_host <hostname>`). Run the Ansible roles declared in `config/external-hosts/<hostname>.yml`, in order. There is no provisioning equivalent because the repository does not provision external hosts; the SSH user used for the connection comes from the host's `identity.ssh_user` field. See [concepts/external-hosts](../concepts/external-hosts.md).

**DNS management** (`terraform_dns <plan|apply>`). Plan or apply the Terraform configuration under `terraform/dns/` that owns the internal DNS zones. This is separate from per-LXC provisioning so that a DNS change can be applied without touching any container.

**Hypervisor configuration** (`ansible_pve`). Run Ansible against the Proxmox host itself. Used for host-level concerns that are not specific to any container.

**Repository linting** (`./run/lint`). Run the suite of static checks against the working tree. This is the one operation that is safe to run on a developer machine, since it neither reads secrets nor writes state.

A few smaller operations exist for plumbing — `ntfy_workflow_status` for workflow notifications, `render_lxc_playbook` and `render_external_host_playbook` for generating per-host playbooks on demand — and are not normally invoked by hand.

## Lifecycle of the image

The image is built when `runner-toolbox/` sources change, not on every apply. Builds happen on the runner via `.github/workflows/_build_runner_image.yml`; the resulting image stays on the runner's local docker daemon and is reused across operations until the next rebuild. There is no garbage collection beyond ordinary docker housekeeping.

A consequence is that an apply can fail because the toolbox image is older than the wrapper expects. The remedy is to rebuild the image; `./run/lint` does this automatically the first time it runs, which is the easiest way to ensure a fresh image is present.

## Adding tools

Adding a tool to the toolbox is a change to `runner-toolbox/Dockerfile` and `runner-toolbox/pyproject.toml`. After the change, the next image build picks the tool up. Wrapper scripts under `runner-toolbox/scripts/` that want to use the new tool should also be updated; otherwise the tool is present but unused.

Tools that are useful only on a developer machine — IDE plugins, formatters that are not part of the lint suite — do not belong in the toolbox. The codeowner keeps the toolbox focused on the apply path because that is what makes its contents easy to reason about.
