# LXC schema

Each container is fully described by one YAML file named after its VMID. The file is consumed by both control planes — Terraform reads the provisioning portion, Ansible reads the configuration portion — and is the single source of truth for "what is this container".

This document describes the schema. For the rationale behind the model, see [concepts/architecture](../concepts/architecture.md). For the procedural walkthrough of using it, see [runbooks/add-service](../runbooks/add-service.md).

## Top-level shape

A container file has up to three top-level sections:

- A **provisioning** section, consumed by Terraform, declaring how the container is shaped on Proxmox.
- An optional **hypervisor extras** section, consumed by Terraform, used for per-container Proxmox configuration that is not exposed through the standard provisioning fields (mount point lines, cgroup device permissions, kernel-level entries).
- A **configuration** section, consumed by Ansible, declaring the roles to apply once the container is running.

A file with only the provisioning section produces a bare container. A file without a configuration section is well-formed but rarely useful — the container exists but is not configured.

## Provisioning fields

The provisioning section names the container and declares its resources and network attachment. The required fields express identity (the VMID, hostname, address, and upstream resolver) and the resource envelope (CPU, memory, swap, root filesystem size). Optional fields cover behaviour at host boot, the privileged-versus-unprivileged choice, and any additional mount points beyond the root filesystem.

Two conventions are worth knowing:

- The container's address is given with its CIDR mask. The mask reflects the homelab subnet, not a per-container choice; it should match what every other container uses.
- The unprivileged default is the right answer unless a specific feature requires otherwise. GPU passthrough is the usual reason to flip it.

## Mount points

Mount points expose host directories inside the container. Each mount point declares an index, a host-side source, a container-side target, and a size. Indexes are small integers used by Proxmox to slot the mounts; the convention in this repository is to start at one. The size field caps how much the container can write — useful for shared pool storage, less relevant for read-mostly mounts.

Mount points declared here are visible to Terraform and Proxmox in the standard way. Mount entries declared in the *hypervisor extras* section (see below) are an alternative path used when a non-standard form is required, for example to disable backup of a particular mount.

## Hypervisor extras

The hypervisor extras section is an escape hatch for things that have to be expressed as raw lines in the Proxmox container configuration. The two recurring uses are:

- **Hardware exposure** — granting the container access to specific device classes (GPUs, the `tun` device for VPN containers, USB peripherals) by declaring cgroup device permissions and bind mounts of the relevant device files.
- **Non-standard mount declarations** — mount entries that need flags the structured mount-points form does not expose, such as opting a mount out of backup.

This section is intentionally lower-level than the rest of the schema. Edits here should be informed by the relevant Proxmox documentation; the homelab does not validate them beyond passing them through.

## Configuration section

The configuration section declares the Ansible roles to apply, in order. Each entry is either a bare role name (when the role's defaults are sufficient) or a role-with-variables form, where the role name is paired with a map of variable overrides specific to this container.

Variable values can pull from the runner's environment to surface secrets without committing them to the repository. This is how credentials reach the container; see [concepts/secrets-and-state](../concepts/secrets-and-state.md).

The order of roles is significant — they execute in the order listed, and the conventional order is base setup, then container runtime if needed, then hardware drivers if needed, then service-specific roles. See [concepts/service-lifecycle](../concepts/service-lifecycle.md).

A small inline-tasks form exists for one-off configuration that does not justify a role. Use it sparingly; when it grows past a handful of tasks, lift it into a role.

## VMID ranges

The VMID space is partitioned by purpose: a low range for infrastructure containers, a middle range for applications, a high range for runners. The ranges are conventions, not enforced limits, and exist so that an operator looking at a number can immediately tell what kind of container it is. See [concepts/networking](../concepts/networking.md) for the addressing model that the VMID feeds into.

## What the schema does not describe

The schema describes a container at rest: what it is, what shape it has, what configuration it should converge to. It does not describe operational state (whether the container is currently running), runtime metrics, or the relationship between containers. Cross-cutting concerns — DNS records, reverse-proxy entries, monitoring scrape targets — live in their own files and are linked to a container only through the VMID-as-identity convention.

A container file is not a complete description of a *service*. A service exists when its container exists and the cross-cutting entries that make it discoverable exist. See [concepts/service-lifecycle](../concepts/service-lifecycle.md).
