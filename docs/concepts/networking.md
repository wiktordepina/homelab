# Networking

The homelab assumes a flat routed network is provided to it. It does not configure routing, gateways, or upstream resolution. This document describes the conventions the homelab itself imposes on top of that fabric.

## Assumed fabric

A `10.20.0.0/16` network is available, with a gateway and an upstream resolver, supplied by an external router that is out of scope for this repository. The Proxmox host has management connectivity on a separate management network. Both are taken as given.

Containers attach to the homelab subnet via a Proxmox bridge. The bridge configuration is part of the host's hypervisor setup and not managed here.

## VMID is identity

The most important convention is that the container ID is the service's identity. The same number determines:

- The container's IP address, by a fixed mapping into the homelab subnet.
- The hostname under the internal DNS zone.
- The file in which the container is declared (named after the VMID).
- The runner-toolbox invocations that target the container.

This rule is rigid because every other convenience in the system depends on it. Knowing the VMID lets the operator predict everything else about the container without consulting any table. Breaking the mapping does not just inconvenience the operator; it silently misroutes DNS, monitoring, and the SSH targets that the runner uses to reach containers.

A small number of infrastructure containers (the internal nameserver, the reverse proxy) sit at addresses that are deliberately memorable rather than VMID-derived. These are the only exceptions; they are baked into the fabric and not expected to grow in number.

## Address ranges

The VMID space is partitioned by purpose, not by allocation. The ranges are conventions, not enforced limits.

- The lowest range is reserved for **infrastructure** containers — services that other services depend on, such as DNS and the reverse proxy.
- The middle range is reserved for **applications** — the services that exist for their own sake.
- The highest range is reserved for **runners** — self-hosted GitHub Actions executors.

Allocating a VMID is a small act of design: the operator picks a free number in the appropriate range and that number becomes the service's identity for as long as the service exists.

## Internal name resolution

Containers resolve internal names through a homelab-resident nameserver, not through the upstream router's resolver. The internal zone exists so that services can find each other by name without depending on anything outside the homelab. Operators on the LAN, configured to use the same nameserver, see the same names.

Containers also resolve external names through the same internal resolver, which forwards upstream. There is no split-horizon or per-container resolver configuration; everything goes through the one nameserver. If it is down, the homelab cannot resolve names — that is acknowledged risk, mitigated by keeping the resolver simple.

The Proxmox host does not use the internal resolver. It resolves names through its own upstream configuration. This is occasionally surprising when troubleshooting from the host, and is by design: the host's reachability should not depend on a service running on top of itself.

## Traffic flow at a glance

Traffic to a service can arrive through three paths, described in detail in [domains-and-tls](domains-and-tls.md):

- **Direct internal access** by name or address, used by other containers and by operators on the LAN who do not need TLS.
- **LAN-side reverse proxy**, terminating TLS for browsers on the LAN that prefer named, encrypted endpoints.
- **Public Cloudflare Tunnel**, for the small set of services that are intentionally exposed to the internet.

Outbound traffic from containers goes through the upstream router and is not shaped or filtered by this repository.
