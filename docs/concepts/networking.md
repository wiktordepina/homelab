# Networking

The homelab assumes a flat routed network is provided to it. It does not configure routing, gateways, or upstream resolution. This document describes the conventions the homelab itself imposes on top of that fabric.

## Assumed fabric

A `10.20.0.0/16` network is available, with a gateway and an upstream resolver, supplied by an external router that is out of scope for this repository. The Proxmox host has management connectivity on a separate management network. Both are taken as given.

Containers attach to the homelab subnet via a Proxmox bridge. The bridge configuration is part of the host's hypervisor setup and not managed here.

## VMID is identity

The most important convention is that the container ID is the service's identity. The same number determines:

- The container's IP address, by a fixed mapping into the homelab subnet (`10.20.1.<vmid>`).
- The hostname under the internal DNS zone (`<hostname>.home.matagoth.com`).
- The file in which the container is declared (`config/lxc/<vmid>.yaml`, named after the VMID).
- The arguments to the runner-toolbox scripts (`terraform_lxc <vmid>`, `ansible_lxc <vmid>`) that target the container.

The codeowner treats this rule as rigid because every other convenience in the system depends on it. Knowing the VMID lets you predict everything else about the container without consulting any table. Breaking the mapping does not just inconvenience whoever is operating the homelab; it silently misroutes DNS, monitoring, and the SSH targets that the runner uses to reach containers.

A small number of infrastructure containers (the internal nameserver, the reverse proxy) sit at addresses that are deliberately memorable rather than VMID-derived. These are the only exceptions; they are baked into the fabric and not expected to grow in number.

A second, narrower carve-out exists for containers whose workload depends on a kernel subsystem the kernel itself scopes to the init network namespace — Bluetooth being the canonical example, where the bluetooth core unconditionally rejects socket creation outside `init_net`. Containers in that position cannot get their own netns at all; they share the host's, which means they have no VMID-derived address and no internal DNS record. They are reached through the hypervisor's container console rather than via SSH on the homelab subnet. This is an acknowledged trade — the alternative is moving the workload off the LXC fleet entirely — and the exception is captured per-container in `pve_extra` so that the YAML still describes the truth about how the container is shaped.

## Address ranges

The VMID space is partitioned by purpose, not by allocation. The ranges are conventions, not enforced limits.

- **`100–199`** is reserved for **infrastructure** containers — services that other services depend on, such as DNS and the reverse proxy.
- **`200–499`** is reserved for **applications** — the services that exist for their own sake.
- **`500–599`** is reserved for **runners** — self-hosted GitHub Actions executors.

Allocating a VMID is a small act of design: pick a free number in the appropriate range and that number becomes the service's identity for as long as the service exists.

## Internal name resolution

Containers resolve internal names through a homelab-resident nameserver, not through the upstream router's resolver. The internal zone exists so that services can find each other by name without depending on anything outside the homelab. Anyone on the LAN, configured to use the same nameserver, sees the same names.

Containers also resolve external names through the same internal resolver, which forwards upstream. There is no split-horizon or per-container resolver configuration; everything goes through the one nameserver. If it is down, the homelab cannot resolve names — that is a risk the codeowner accepts, mitigated by keeping the resolver simple.

The Proxmox host does not use the internal resolver. It resolves names through its own upstream configuration. This is occasionally surprising when troubleshooting from the host, and is a deliberate choice by the codeowner: the host's reachability should not depend on a service running on top of itself.

## Traffic flow at a glance

Traffic to a service can arrive through three paths, described in detail in [domains-and-tls](domains-and-tls.md):

- **Direct internal access** by name or address, used by other containers and by anyone on the LAN who does not need TLS.
- **LAN-side reverse proxy**, terminating TLS for browsers on the LAN that prefer named, encrypted endpoints.
- **Public Cloudflare Tunnel**, for the small set of services that are intentionally exposed to the internet.

Outbound traffic from containers goes through the upstream router and is not shaped or filtered by this repository.
