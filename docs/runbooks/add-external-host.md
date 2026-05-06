# Add an external host

An external host is a physical machine outside the Proxmox host that this repository configures through the configuration control plane only. This runbook is the procedural walkthrough; for the model behind it, see [concepts/external-hosts](../concepts/external-hosts.md). For the schema, see [reference/external-host-schema](../reference/external-host-schema.md).

The same lockstep applies, in reverse, to removing an external host. A short section at the end covers updates and removal.

## Prerequisites — what must be done by hand first

Unlike an LXC, the repository does not bring an external host into existence. The following steps happen on the physical machine before this runbook applies, and are documented in the host's YAML under `manually_provisioned:` so that the requirement is visible at the declaration.

1. **Install an operating system.** Anything Ansible-friendly is fine; the codeowner's habit on Raspberry Pi hardware is Raspberry Pi OS Lite (64-bit).
2. **Configure the network** so that the machine has a stable address and is reachable from the runner. Static IP at the host or DHCP reservation at the router are both acceptable; the address you settle on is what goes into the YAML.
3. **Authorise the runner's SSH key.** The runner connects as the SSH user named in the YAML (typically `root` for single-purpose machines). Add the runner's public key to that user's `~/.ssh/authorized_keys` so password-less SSH works from the runner.
4. **Confirm reachability.** From the runner, `ssh <ssh_user>@<ip>` should succeed without a password and drop you at a shell on the host.

When all four are true, the host is ready to be declared.

## The lockstep, for a new external host

A new external host touches the following layers. All of them belong in one commit; partial commits leave the homelab in a half-deployed state.

1. **Host declaration.** Add `config/external-hosts/<hostname>.yml`, declaring identity, manually-provisioned aspects, and the Ansible roles that should configure the host. The schema is in [reference/external-host-schema](../reference/external-host-schema.md).
2. **Configuration role, if needed.** If no existing role fits, add one under `ansible/roles/<name>/`, following the standard role layout. Most external hosts reuse `base` plus a service-specific role.
3. **Internal DNS record.** Add an `A` record under `terraform/dns/external_hosts.tf` mapping `<hostname>.home.matagoth.com` to the host's address. Without this, no other container can resolve the host by name.
4. **Reverse proxy entry**, if the host serves a UI intended for browser access. Same two coordinated edits as for an LXC service: an entry in the `nginx_reverse_proxy` role's variables that maps the friendly name to the host's backend address, and a record under `terraform/dns/reverse_proxy.tf` that points `<hostname>.homelab.matagoth.com` at the proxy.
5. **Monitoring scrape**, if the host exposes metrics. Add a scrape entry under the `prometheus` role pointing the metrics collector at the host.
6. **CI matrix.** Add the new hostname to the external-host matrix in `.github/workflows/homelab_iac.yml` so routine applies include it.
7. **Secrets**, if any role on the host needs them. Same pattern as for LXCs — credentials in `/pve/secrets/` on the runner, referenced via `lookup('ansible.builtin.env', '<NAME>')` from the role's variables.

## Applying the changes

Once the lockstep edits are committed and pushed, the GitHub Actions workflow in `.github/workflows/homelab_iac.yml` applies them. For applying a single host by hand from the runner:

```bash
# Per-external-host configuration
./run/execute_runner ansible_external_host <hostname>

# Diagnostics: render the per-host playbook without running it
./run/execute_runner render_external_host_playbook <hostname>
```

DNS is applied via the existing DNS control plane:

```bash
./run/execute_runner terraform_dns plan
./run/execute_runner terraform_dns apply
```

Each operation is independently re-runnable. There is no provisioning operation for an external host, because the repository does not provision the machine.

## Worked example: a new external host

Adding `pi-01`, a Raspberry Pi 4B at `10.10.50.10`, with no role beyond the common `base` for now. (A subsequent change adds the service-specific role; this example covers only the onboarding lockstep.)

### 1. Host declaration

`config/external-hosts/pi-01.yml`:

```yaml
---
identity:
  hostname: pi-01
  fqdn: pi-01.home.matagoth.com
  ip: 10.10.50.10
  ssh_user: root

manually_provisioned:
  - operating_system        # Raspberry Pi OS Lite (64-bit)
  - network_configuration   # static IP 10.10.50.10 set on the host
  - ssh_authorized_keys     # runner's public key added to /root/.ssh/authorized_keys

ansible:
  roles:
    - base

notes: |
  Raspberry Pi 4B (8GB RAM). General-purpose external host.
  Lives outside the Proxmox host because some intended workloads
  (e.g. Bluetooth, GPIO sensors) need hardware the hypervisor does
  not have.
```

### 2. Internal DNS

In `terraform/dns/external_hosts.tf`:

```terraform
resource "dns_a_record_set" "pi_01" {
  zone      = "home.matagoth.com."
  name      = "pi-01"
  addresses = ["10.10.50.10"]
  ttl       = 500
}
```

### 3. CI matrix

In `.github/workflows/homelab_iac.yml`, append `pi-01` to the external-host matrix.

### 4. Apply

```bash
./run/execute_runner ansible_external_host pi-01
./run/execute_runner terraform_dns apply
```

### 5. Verify

```bash
# Host is reachable by name on the internal zone from another container
dig @10.20.1.201 pi-01.home.matagoth.com

# Host has converged: base role applied
ssh root@pi-01.home.matagoth.com hostnamectl
```

## Subnet note

The codeowner's external hosts may live on a different subnet from the LXC fleet (the LXC fleet sits on `10.20.0.0/16`; a Raspberry Pi on the general-purpose LAN typically sits on `10.10.0.0/16` or similar). Both subnets are routed by the upstream OpenSense device, so reachability across subnets is a router concern, not a homelab concern. If a new external host turns out not to be reachable from the LXC fleet, the first place to check is the routing rules on the upstream device, not anything in this repository.

## Verifying the host is done

An external host is done when:

- It is reachable by name on the internal zone from another container.
- The roles declared in its YAML have all converged.
- It is reachable through the proxy if it serves a UI.
- It appears in monitoring if it exposes metrics.
- It is included in the next routine deploy.

Anything less is a half-deployed host. The lockstep is what makes "done" reliable, the same as for an LXC service.

## Modifying an existing external host

Updating an external host follows the same control-plane boundaries as updating an LXC, minus the provisioning plane that does not exist for external hosts:

- **Role or stack content changes** are configuration concerns; re-apply configuration on the host with `ansible_external_host <hostname>`.
- **Cross-cutting changes** (DNS, reverse proxy, monitoring) follow the lockstep and are applied through their respective control planes.
- **Hardware or operating-system changes** are out of scope for this repository; update the `manually_provisioned:` list in the YAML to reflect the new state.

## Removing an external host

Removal is the lockstep in reverse:

1. **Remove cross-cutting references first** — CI matrix, monitoring scrape, reverse-proxy entries, internal DNS record. Apply each through its respective control plane.
2. **Stop applying configuration** to the host. There is nothing to destroy in IaC; the physical machine continues to exist regardless of what this repository does.
3. **Delete `config/external-hosts/<hostname>.yml`** as the final cleanup.
4. **Decommission the physical machine** by hand if appropriate.

Because there is no destruction step in IaC, the order is less load-bearing than for LXCs — the repository simply forgets the host once the YAML is gone.
