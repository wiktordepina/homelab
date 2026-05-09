# VM schema

The homelab provisions full Proxmox QEMU VMs alongside LXCs for workloads that genuinely need a separate kernel. Each VM is fully described by one YAML file at `config/vm/<vmid>.yaml`, named after its VMID. The schema is similar to the LXC one — same VMID-as-identity convention, same Terraform/Ansible split, same per-VMID statefile — and intentionally deviates only where the underlying technology forces it to.

This document describes the schema. For when to choose a VM over an LXC, see *Choosing a VM over an LXC* below. For the procedural walkthrough, see [runbooks/add-service](../runbooks/add-service.md). For the bootstrap procedure that produces the cloud-init template VMs clone from, see [runbooks/build-vm-template](../runbooks/build-vm-template.md).

## Top-level shape

A VM file has two top-level sections:

- A **provisioning** section, consumed by Terraform, declaring how the VM is shaped on Proxmox.
- A **configuration** section, consumed by Ansible, declaring the roles to apply once the VM is running.

The two top-level keys are `terraform:` and `ansible:`. There is no `pve_extra:` analog as there is for LXCs — VMs do not need an escape hatch into raw Proxmox config because the structured fields cover the cases where one would be reached for (USB pass-through, multi-NIC, additional disks).

## Provisioning fields

Provisioning declares VM identity, resources, network attachment, and any hardware pass-through.

Identity fields (VMID, hostname, IP, nameserver) follow the same rules as LXCs: VMID is the address by the `10.20.1.<vmid>` mapping, hostname determines the internal DNS record, the address is given with its `/16` mask. The provisioning section never declares the SSH key — that is injected by the runner from its own environment, the same way it is for LXCs.

Resource fields cover CPU sockets and cores, memory, and the rootfs disk size. Defaults are sized for a small Linux daemon (1 socket, 1 core, 1 GiB RAM, 8 GiB disk); override per-VM where the workload needs more.

The clone source defaults to `tmpl-debian-13-cloudinit` (VMID 9000, see the [build-vm-template runbook](../runbooks/build-vm-template.md)). Override `template` only when a workload genuinely needs a different base image; building the alternative template is itself a one-off procedure that has to happen first.

## Cloud-init

VMs use cloud-init for first-boot configuration. The provider populates the cloud-init drive on each apply with the VM's network configuration (`ipconfig0`), upstream nameserver, and the runner's SSH public key. There is no per-VM cloud-init customisation knob — every VM gets the same shape, and per-VM behaviour belongs in the Ansible roles, not in cloud-init. Keeping cloud-init minimal preserves the Terraform/Ansible split: cloud-init exists only to get a freshly cloned VM to a state Ansible can SSH into.

## Network attachments

The default attachment matches LXC conventions: one virtio NIC on `vmbr1`, the homelab's guest bridge. Multi-NIC VMs (network monitoring, captive portals) declare `extra_networks` exactly as LXCs do.

Conventions for extra interfaces are the same as for LXCs (DMZ-on-eth0, no gateway on extras, `<subnet>.250.<vmid>` for secondary presence on a non-DMZ subnet). The single-interface default is the right answer unless the workload genuinely needs multi-subnet visibility.

## USB pass-through

A VM can declare a list of USB devices to pass through under `usb_passthrough`, each entry an object with a `host` selector in the form `vendor_id:product_id` (e.g. `37ad:0600`). Pass-through happens at the QEMU level — the guest sees a real USB device with full kernel-driver support, no cgroup or bind-mount setup required and no privileged-container caveats.

This is the cleanest of the homelab's hardware pass-through paths and is the principal motivation for keeping VM provisioning in the IaC.

## Configuration section

The `ansible:` section is identical in shape to the LXC equivalent: a list of roles to apply, in order, with optional per-role variable overrides. Variables can pull secrets from the runner's environment via `lookup('ansible.builtin.env', '<NAME>')`. Roles target the VM over SSH on its `10.20.1.<vmid>` address, the same way they target LXCs — meaning a role written for an LXC works in a VM with no changes, as long as it does not rely on LXC-specific kernel features.

## VMID ranges

Same partitioning as for LXCs (`100–199` infrastructure, `200–499` applications, `500–599` runners). VMs and LXCs share the VMID space because Proxmox enforces VMID uniqueness across both; the kind of guest is implementation detail, identity is what matters.

VM templates live in a separate range starting at `9000` and are not addressable as services — they are not in DNS, not in the proxy, not in monitoring. The template the default schema clones from is documented in the [build-vm-template runbook](../runbooks/build-vm-template.md).

## Choosing a VM over an LXC

Default to an LXC. Pick a VM only when one of these applies:

- The workload depends on a kernel subsystem the host kernel restricts to its own namespace. Bluetooth is the canonical example: the kernel rejects `AF_BLUETOOTH` socket creation outside `init_net`, with no capability or seccomp knob to bypass. Anything that has to live in its own netns and use Bluetooth must be a VM.
- The workload needs to load kernel modules the host should not be carrying. The host is intentionally a hypervisor, not a service host; modules accumulated on it grow the host's surface area. A VM keeps that scoped.
- The workload needs a kernel different from the host's — different version, different patches, different tunables. LXCs share the host kernel by design.
- The workload's USB pass-through is fragile inside an LXC. The cgroup-and-bind dance works for keyboards, mice, and many DVB tuners, but advanced devices (Bluetooth chipsets, devices that hot-replug, anything with firmware that loads after kernel attach) are routinely smoother in a VM.

The cost of a VM is roughly 512 MiB extra RAM minimum, ~30 seconds slower boot, and a slightly heavier disk footprint. None of these matters at homelab scale, but the cumulative drift if every workload moved to VMs would. Default LXC, escalate when forced.

## What the schema does not describe

As with LXCs, the schema describes a VM at rest. Operational state, runtime metrics, and the relationship between VMs and the rest of the homelab live in separate files (DNS, reverse proxy, monitoring, CI matrix), wired together only through the VMID. A VM file is not a complete description of a service; the service exists when the VM exists *and* the cross-cutting entries that make it discoverable exist.
