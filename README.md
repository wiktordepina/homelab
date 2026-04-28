# Homelab

Infrastructure-as-code for a single-host Proxmox homelab. Each service runs in its own LXC container, declared by one YAML file per container ID, and reconciled by Terraform and Ansible from a self-hosted GitHub Actions runner.

## Why this exists

The homelab evolved out of years of hand-configured services on a single Proxmox host. The repository is the result of capturing that steady state as code: anything that runs on the host should be expressible here, so that the system is legible, auditable, and reproducible — by the operator, by future-them, and by anyone they choose to bring in.

It is deliberately scoped to a single host and a single operator. It is not a Kubernetes cluster, a multi-tenant platform, or a turnkey homelab template. It is one person's setup, written down honestly.

## Fundamental principles

These do not change. They shape every other decision.

1. **VMID is identity.** A service's container ID determines its IP, its DNS name, and its place in the operator's mental model.
2. **The runner is the only execution surface.** Secrets and state live on the runner. Laptops can lint and reason about code; they cannot apply.
3. **Lockstep additions.** Adding a service touches code across several layers (provisioning, configuration, DNS, reverse proxy, monitoring, CI). All of them or none of them.
4. **One YAML per container.** A container is fully described by a single file named after its VMID.
5. **IaC for everything except public exposure.** The Cloudflare Tunnel route table is the one carve-out, and it is acknowledged rather than hidden.

## Where to read next

Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). It explains the model and indexes the rest of the documentation by category — concepts (the *why*), references (the *shape*), and runbooks (the *how*).
