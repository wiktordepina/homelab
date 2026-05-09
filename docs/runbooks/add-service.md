# Add a service

A service is added in lockstep across several layers of the repository, then applied through the runner. This runbook is the procedural walkthrough; for the model behind it, see [concepts/service-lifecycle](../concepts/service-lifecycle.md).

The same lockstep applies, in reverse, to removing a service. A short section at the end covers updates and removal.

## Decide before editing

Two decisions are worth making before touching any files.

**LXC, VM, or stack?** Default to an LXC. Pick a VM (`config/vm/<vmid>.yaml`) only when the workload needs a separate kernel — anything that depends on a kernel subsystem the host scopes to its own namespace (Bluetooth being the canonical example), needs to load modules the host should not be carrying, or needs USB pass-through smoother than LXC's cgroup/bind dance can deliver. The decision rule is in [reference/vm-schema](../reference/vm-schema.md). Pick a stack under `config/docker/<name>/` for small docker-compose units that can share a host with similar services; the reasoning is in [reference/docker-stacks](../reference/docker-stacks.md).

**Pick a VMID.** Choose a free number in the appropriate range: `100–199` for infrastructure, `200–499` for applications, `500–599` for runners. The number becomes the service's identity (its address `10.20.1.<vmid>`, its hostname under `home.matagoth.com`, its file `config/lxc/<vmid>.yaml` or `config/vm/<vmid>.yaml`) for as long as the service exists; choose deliberately. VMs and LXCs share the VMID space — Proxmox enforces uniqueness across both.

For a stack, no VMID is allocated — the stack inherits the host LXC's identity.

## The lockstep, for a new LXC

A new LXC service touches the following layers. All of them belong in one commit; partial commits leave the homelab in a half-deployed state.

1. **Container declaration.** Add `config/lxc/<vmid>.yaml`, declaring the provisioning fields under `terraform:` and the Ansible roles under `ansible:` that should configure the container. The schema is in [reference/lxc-schema](../reference/lxc-schema.md).
2. **Configuration role, if needed.** If no existing role fits, add one under `ansible/roles/<name>/`, following the standard role layout (`tasks/`, `handlers/`, `vars/`, `defaults/`, `templates/`, `files/`, `README.md`). Most services do not need a new role; they reuse `base`, the container runtime (`docker`), and a service-specific or generic role.
3. **Internal DNS record.** Add an `A` record under `terraform/dns/services.tf` mapping `<hostname>.home.matagoth.com` to `10.20.1.<vmid>`. Without this, no other container can resolve the service by name.
4. **Reverse proxy entry**, if the service has a browser UI. Two coordinated edits are needed: an entry in the `nginx_reverse_proxy` role's variables that maps the service's friendly name to its backend address, and a record under `terraform/dns/reverse_proxy.tf` that points `<hostname>.homelab.matagoth.com` at the proxy. See [concepts/reverse-proxy](../concepts/reverse-proxy.md) for what the proxy expects of a backend and which classes of service have known footguns.
5. **Monitoring scrape**, if the service exposes metrics. Add a scrape entry under the `prometheus` role pointing the metrics collector at the service's address.
6. **CI matrix and dispatch dropdown.** Add the new VMID to the deploy workflow's matrix in `.github/workflows/homelab_iac.yml` so routine applies include it, and add an `<vmid> - <hostname>` entry to the `workflow_dispatch.vmid.options` list in `.github/workflows/_lxc.yml` (or `_vm.yml` for a VM) so manual dispatch picks the right host without a lookup. Lint enforces 1:1 between the YAML files and the dropdown — drift fails CI.
7. **Secrets**, if the service needs them. Add the credentials to `/pve/secrets/` on the host in the same shell-script form as the others, and reference them from the role's variables (via `lookup('ansible.builtin.env', '<NAME>')`) or from a templated environment value in the relevant compose file.

Anything genuinely service-specific that you would need to know later — credentials it needs, manual steps after first apply, idiosyncratic upstream behaviour — is captured either in the role's notes or in the [post-deploy-setup runbook](post-deploy-setup.md).

## The lockstep, for a new VM

A VM service touches the same layers as an LXC, with two structural differences: the declaration lives under `config/vm/<vmid>.yaml`, and the `bluetooth_host`-style host-side companion role of an LXC special case is not needed because VMs have their own kernel.

1. **VM declaration.** Add `config/vm/<vmid>.yaml`. Schema and field reference: [reference/vm-schema](../reference/vm-schema.md). USB pass-through, when needed, is declared as a list under `usb_passthrough:` — no host-side cgroup or bind-mount setup required.
2. **Configuration role, if needed.** Roles target the VM over SSH on the same `10.20.1.<vmid>` address as for LXCs; an Ansible role written for an LXC works inside a VM unchanged unless it relies on LXC-specific kernel behaviour.
3. **Internal DNS, reverse proxy, monitoring scrape, secrets.** Identical to the LXC procedure; the kind of guest is invisible to these layers.
4. **CI matrix and dispatch dropdown.** Add the VMID under the `DeployVMs` job in `.github/workflows/homelab_iac.yml` (separate matrix from `DeployLXCs`), and add an `<vmid> - <hostname>` entry to `workflow_dispatch.vmid.options` in `.github/workflows/_vm.yml`. Lint enforces 1:1 between the per-VMID YAML files and the dropdown.
5. **Cloud-init template.** A VM clones from the default Debian template at VMID 9000. If it does not yet exist, build it once via [build-vm-template](build-vm-template.md) — this is a one-off bootstrap, not part of every-service procedure.

Apply the VM the same way as an LXC, replacing `terraform_lxc`/`ansible_lxc` with `terraform_vm`/`ansible_vm`:

```bash
./run/execute_runner terraform_vm <vmid> apply
./run/execute_runner ansible_vm <vmid>
```

## The lockstep, for a stack on a shared host

A stack is lighter. The layers it touches:

1. **Stack definition.** Add a directory `config/docker/<name>/` with a `docker-compose.yaml` and any supporting files. Templated environment values reference secrets that exist in `/pve/secrets/` on the runner.
2. **Host LXC reference.** Edit the host LXC's `config/lxc/<vmid>.yaml` to list the new stack's identifier in the `containers:` variable of the `containers` role with state `up`. The next `ansible_lxc <vmid>` on that host picks it up.
3. **Internal DNS, reverse proxy, monitoring, secrets** — same as for an LXC service, with the difference that the address points at the host LXC and the port is the one the stack publishes.

A stack does not get its own VMID, its own CI-matrix entry, or its own configuration role.

## Applying the changes

Once the lockstep edits are committed and pushed, the GitHub Actions workflow in `.github/workflows/homelab_iac.yml` applies them. For the impatient, or when applying only one piece at a time, `./run/execute_runner` offers per-control-plane operations. The order matters when applying by hand:

1. **`terraform_lxc <vmid> apply`** first — the container has to exist before it can be configured.
2. **`ansible_lxc <vmid>`** second — once the container exists and is reachable.
3. **`terraform_dns apply`** at any point after provisioning, since DNS records resolve to addresses that exist as soon as Terraform has assigned them.
4. **`ansible_lxc 110`** (the reverse-proxy host) after the new backend is configured and reachable, otherwise the proxy will return errors when it forwards.

Each operation is independently re-runnable. If something fails, fix it and run the relevant operation again; do not run them all back to back as a recovery.

The full set of `./run/execute_runner` operations:

```bash
# Per-LXC provisioning
./run/execute_runner terraform_lxc <vmid> plan
./run/execute_runner terraform_lxc <vmid> apply
./run/execute_runner terraform_lxc <vmid> destroy

# Per-LXC configuration
./run/execute_runner ansible_lxc <vmid>

# Per-VM provisioning
./run/execute_runner terraform_vm <vmid> plan
./run/execute_runner terraform_vm <vmid> apply
./run/execute_runner terraform_vm <vmid> destroy

# Per-VM configuration
./run/execute_runner ansible_vm <vmid>

# Cross-cutting DNS
./run/execute_runner terraform_dns plan
./run/execute_runner terraform_dns apply

# Hypervisor configuration
./run/execute_runner ansible_pve

# Diagnostics: render the per-host playbook without running it
./run/execute_runner render_lxc_playbook <vmid>
./run/execute_runner render_vm_playbook <vmid>
```

## Worked example: a new dedicated-LXC service

Adding a hypothetical `myservice` on VMID 212 with a docker-compose stack and a browser UI proxied at `myservice.homelab.matagoth.com`. The lockstep below is a single commit covering all the layers.

### 1. Container declaration

`config/lxc/212.yaml`:

```yaml
---
terraform:
  vmid: 212
  hostname: myservice
  ip_address: 10.20.1.212/16
  nameserver: 10.20.0.1
  cpu_core_count: 4
  memory: 4096
  swap: 512
  start_on_boot: true
  rootfs_size: 50G

ansible:
  roles:
    - base
    - docker
    - role: containers
      vars:
        containers:
          - name: myservice
            state: up
```

### 2. Stack definition

`config/docker/myservice/docker-compose.yaml`:

```yaml
---
services:
  myservice:
    image: myimage:latest
    container_name: myservice
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - myservice_data:/data
    environment:
      - API_KEY={{ lookup('ansible.builtin.env', 'MYSERVICE_API_KEY') }}

volumes:
  myservice_data:
```

Templated environment values are evaluated by Ansible at apply time; the secret is sourced from `/pve/secrets/<file>.sh` on the runner.

### 3. Internal DNS

In `terraform/dns/services.tf`:

```terraform
resource "dns_a_record_set" "myservice" {
  zone      = "home.matagoth.com."
  name      = "myservice"
  addresses = ["10.20.1.212"]
  ttl       = 500
}
```

### 4. Reverse proxy entry

In `terraform/dns/reverse_proxy.tf`, point the LAN-side proxy zone hostname at the proxy's address. The corresponding upstream entry goes into the `nginx_reverse_proxy` role's variables (under `ansible/roles/nginx_reverse_proxy/`), naming the friendly host and its `10.20.1.212:8080` backend.

### 5. Apply

```bash
./run/execute_runner terraform_lxc 212 plan
./run/execute_runner terraform_lxc 212 apply
./run/execute_runner ansible_lxc 212
./run/execute_runner terraform_dns apply
./run/execute_runner ansible_lxc 110   # reverse proxy reload
```

### 6. Verify

```bash
# Resolves on the internal zone from another container
dig @10.20.1.201 myservice.home.matagoth.com

# Reachable through the proxy with a valid certificate
curl -I https://myservice.homelab.matagoth.com
```

## Worked example: a stack on a shared host

For a small service that fits onto an existing docker host (LXC 205, `dockerhost`), the change is much smaller — no new VMID, no new DNS for the host, just two coordinated edits.

### 1. Stack definition

`config/docker/wallos/docker-compose.yaml` — define the compose unit as for any other stack.

### 2. Reference from the host LXC

In `config/lxc/205.yaml`, append to the `containers:` list of the `containers` role:

```yaml
ansible:
  roles:
    - base
    - docker
    - role: containers
      vars:
        containers:
          # ... existing entries
          - name: wallos
            state: up
```

### 3. Apply

```bash
./run/execute_runner ansible_lxc 205
```

If the stack publishes a UI, also add internal DNS, the reverse-proxy entry, and re-run `ansible_lxc 110`. The host's own address is the backend, on whatever port the stack publishes.

## Verifying the service is done

A service is not done when its container is reachable by IP. The check list is:

- Resolves by name on the internal zone from another container.
- Resolves by friendly name on the LAN-side proxy zone, with a valid certificate, and reaches the backend.
- Appears in monitoring if it exposes metrics, and the metrics collector is scraping it successfully.
- Is included in the next routine deploy.
- Any post-deploy manual steps are recorded in [post-deploy-setup](post-deploy-setup.md).

Anything less is a half-deployed service. The lockstep is what makes "done" reliable.

## Modifying an existing service

Updating a service follows the same boundaries the control planes impose:

- **Resource changes** (CPU, memory, mount points) are provisioning concerns; re-apply provisioning. Some changes require a container restart, which Terraform handles.
- **Role or stack content changes** are configuration concerns; re-apply configuration on the relevant LXC. Container images for stacks are pulled anew when the configuration role runs.
- **Cross-cutting changes** (DNS, reverse proxy, monitoring) follow the lockstep and are applied through their respective control planes.

A change that crosses planes still needs all the relevant operations; modifying a service is not a single-button affair.

## Removing a service

Removal is the lockstep in reverse, and the order matters because some steps are reversible and others are not.

1. **Remove cross-cutting references first** — CI matrix, monitoring scrape, reverse-proxy entries, internal DNS records. Apply each through its respective control plane. None of these is destructive; the homelab tolerates being out of sync at this point.
2. **Stop the workload** — for a stack, set its state to `destroyed` in the host LXC's `containers:` list and re-run `ansible_lxc <vmid>`; for an LXC, this step is implicit in the next.
3. **Destroy the container** — `terraform_lxc <vmid> destroy`. This is the irreversible step.
4. **Delete `config/lxc/<vmid>.yaml` and any `config/docker/<name>/` directory** as the final cleanup, after destruction succeeds.

If any step fails or reveals an unexpected dependency, the situation is recoverable until step three. Doing destruction first and discovering a forgotten reference afterwards is how a service ends up half-removed.
