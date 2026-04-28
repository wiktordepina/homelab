# Architecture

This document is the entry point for understanding the homelab. It describes the high-level model in prose and indexes the rest of the documentation by category.

If you are looking for *what to do*, jump to the [runbooks](#runbooks). If you are looking for *why things are the way they are*, start with [concepts](#concepts). If you are looking for *the shape of a configuration artefact*, see [reference](#reference).

## What this is

A single Proxmox VE host running a collection of LXC containers, one per service, declared and reconciled by Terraform and Ansible. The repository is the source of truth for everything that lives on the Proxmox host; nothing of significance is configured by hand on the host itself.

The system is small enough to fit in one operator's head, and the documentation is deliberately kept at that scale. Where a decision is non-obvious, the rationale lives next to the description.

## The model in one paragraph

Each service is described by a single YAML file keyed by its container ID. That file feeds two control planes: Terraform creates and shapes the container on Proxmox, and Ansible configures it once it exists. Cross-cutting concerns — internal DNS, the LAN-side reverse proxy, public exposure, monitoring — are declared separately and updated in lockstep when a service is added or removed. Everything is executed inside a purpose-built container image (the *runner toolbox*) on a self-hosted GitHub Actions runner; that runner is the only place secrets and state exist.

## Boundaries

Some boundaries are load-bearing. They explain why parts of the system look the way they do.

**Host vs. container.** The Proxmox host is treated as a hypervisor, not as a service host. Services run in LXC containers, never directly on the host. The host has its own narrow Ansible target for hypervisor-level concerns; everything else stays in containers.

**Runner vs. laptop.** The full execution path — Terraform applies, Ansible runs, secret access, state mutation — only exists on the runner. A developer laptop can lint and reason about the code, but it cannot apply changes. This is intentional and discussed in [concepts/runner-model](concepts/runner-model.md) and [concepts/secrets-and-state](concepts/secrets-and-state.md).

**IaC vs. manually configured.** Almost everything is declared in this repository. The notable exception is the public-exposure layer (Cloudflare Tunnel routes), which is currently configured by hand in the Cloudflare dashboard. This is acknowledged technical debt; see [concepts/domains-and-tls](concepts/domains-and-tls.md).

## Assumed inputs

This repository describes a steady state. It does not bootstrap from a bare environment. The following are taken as already provided when the IaC runs:

- A routed `10.20.0.0/16` network with a gateway and upstream resolver, supplied by a separate OpenSense device that this repository does not manage.
- A Proxmox VE host with ZFS-backed storage, reachable on the management network, with persistent directories prepared for secrets and Terraform state.
- A registered self-hosted GitHub Actions runner with the secret and state directories mounted into its environment.
- A Cloudflare account and tunnel credential, with any public routes configured manually.

Establishing those inputs is out of scope for this documentation set and will be addressed separately.

## The control planes

Four operational entry points cover everything the runner does:

- **Per-LXC provisioning** — applies the Terraform plan that creates or shapes one container.
- **Per-LXC configuration** — runs the Ansible roles declared by one container's YAML.
- **DNS** — applies the Terraform plan that owns the internal zones.
- **Proxmox host configuration** — runs Ansible against the hypervisor itself.

Each control plane is single-purpose. There is no orchestrator that runs all of them together; ordering and lockstep are the operator's responsibility, guided by the [add-service runbook](runbooks/add-service.md).

## Fundamental principles

These are the non-shifting decisions that shape everything else. They are repeated in the relevant concept docs with rationale, and listed here as a quick orientation.

1. **VMID is identity.** A service's container ID determines its IP, its DNS name, and its place in the operator's mental model. Breaking the mapping breaks the system's legibility.
2. **The runner is the only execution surface.** Secrets and state live on the runner, not on laptops. All applies happen there.
3. **Lockstep additions.** Adding a service touches several files across Terraform, Ansible, DNS, the reverse proxy, monitoring, and CI. Skipping any of them leaves the service half-deployed.
4. **One YAML per container.** A container's full description — resources, mounts, roles, role variables — lives in one file, named after the VMID.
5. **IaC for everything except public exposure.** The Cloudflare Tunnel route table is the one carve-out, and it is acknowledged rather than hidden.

## Documentation index

### Concepts

Durable explanations of *what* and *why*. Read these to build a model of the system.

- [Architecture in depth](concepts/architecture.md) — single-host philosophy, the IaC loop, control planes.
- [Networking](concepts/networking.md) — VMID-as-identity, address ranges, traffic flow, the role of the upstream router.
- [Domains and TLS](concepts/domains-and-tls.md) — the three zones (internal discovery, LAN-side proxy, public), where SSL terminates, what is and is not in IaC.
- [Secrets and state](concepts/secrets-and-state.md) — where they live, why they do not leave the host, what happens when they are missing.
- [Runner model](concepts/runner-model.md) — the toolbox image lifecycle, the lint-versus-apply split, why the runner is the only execution surface.
- [Service lifecycle](concepts/service-lifecycle.md) — the lockstep model, role ordering conventions, addition and removal.
- [Reverse proxy](concepts/reverse-proxy.md) — proxy responsibilities, recurring footguns (WebSockets and similar live-update protocols).

### Reference

Schemas and contracts. Read these to understand the shape of a configuration artefact.

- [LXC schema](reference/lxc-schema.md) — the YAML contract for declaring a container.
- [Runner toolbox](reference/runner-toolbox.md) — what the toolbox provides and how it is invoked, by purpose.
- [Docker stacks](reference/docker-stacks.md) — conventions for stacks running on the shared docker host.

### Runbooks

Procedures. Read these to perform a specific operation.

- [Add a service](runbooks/add-service.md) — the lockstep walkthrough.
- [Create a GitHub Actions runner](runbooks/create-runner.md) — provisioning an additional self-hosted runner.
- [Rotate the wildcard SSL certificate](runbooks/rotate-wildcard-cert.md) — renewal of the LAN-side wildcard cert.
- [Replace a disk in the ZFS pool](runbooks/replace-zfs-disk.md) — physical disk replacement and resilver.
- [Post-deploy service setup](runbooks/post-deploy-setup.md) — manual steps that cannot be expressed in IaC.
- [Troubleshooting](runbooks/troubleshooting.md) — common failure modes and where to look first.
