# Architecture in depth

This document expands on the orientation in [ARCHITECTURE](../ARCHITECTURE.md). Read that one first.

## The IaC loop

The system reconciles itself in three layers, applied in sequence by you when running the wrapper by hand, or by GitHub Actions on push.

**The container exists.** A Terraform plan under `terraform/lxc/`, parameterised by a single per-container YAML in `config/lxc/`, asks the Proxmox provider to create or shape an LXC container. This is provisioning: container ID, hostname, resources, mounts, network attachment. It is idempotent — the second apply is a no-op unless the YAML changed.

**The container is configured.** Once the container exists and is reachable, Ansible runs the roles declared in the same YAML, in the order they are listed. Roles live under `ansible/roles/`. This is configuration: package installation, service files, role-specific variables, anything that has to happen *inside* the container to make it useful. Roles are idempotent and re-runnable.

**Cross-cutting concerns are wired up.** A new container is invisible to the rest of the homelab until it is named in DNS, fronted by the reverse proxy if appropriate, scraped by monitoring, and deployed by CI. Each of these touches a different artefact and each must be edited in lockstep with the container itself. See [service-lifecycle](service-lifecycle.md).

The same loop runs in reverse for removal: cross-cutting references go first, then the Ansible side stops being relevant, then Terraform destroys the container.

## Why two control planes, not one

Terraform and Ansible solve different problems and the codeowner chose to use each for what it is good at. Terraform owns *what exists*: the set of containers, their resources, their network attachments. Ansible owns *what is true inside* each container. Forcing one to do the other's job has been tried elsewhere and produces fragile playbooks (Ansible doing infrastructure) or awkward provisioners (Terraform doing configuration). Keeping the boundary clean keeps each layer small.

The single per-container YAML acts as the bridge. It is consumed by both control planes and they read complementary parts of it.

## The runner as an execution boundary

There is one place in the homelab where applies happen: the self-hosted GitHub Actions runner. The runner has the secrets, has the Terraform state, has SSH access to the containers, and has the Proxmox API token. A laptop has none of these and is intentionally kept that way.

The practical consequence is that the local development loop is read-only: lint the YAML, lint the playbooks, lint the Terraform, push, let CI apply. The tradeoff is a slower iteration cycle. The codeowner accepts this tradeoff because the alternative is sprinkling credentials across machines, which is exactly what the codeowner chose not to do.

See [runner-model](runner-model.md) and [secrets-and-state](secrets-and-state.md) for the consequences of this boundary.

## Why one host, why LXC

The homelab is one box. The codeowner considered a cluster and rejected it: a cluster would introduce orchestration, scheduling, distributed state, and a category of operational concerns that are uninteresting at this scale. One Proxmox host is sufficient and stays sufficient.

LXC is the default for most services because Linux processes benefit from the low overhead and direct kernel access (GPU passthrough, host networking, ZFS mounts). Full VMs are supported alongside LXCs for the cases an LXC cannot serve cleanly: workloads that depend on a kernel subsystem the host kernel scopes to its own namespace (Bluetooth being the canonical example), workloads that need kernel modules the host should not run, or workloads that need a different kernel entirely. The decision rule is in [reference/vm-schema](../reference/vm-schema.md): pick LXC unless something specific forces a VM, and pay the extra memory and slower boot only when you have to.

Containers run *one service each*, with rare exceptions where a shared docker host makes more sense (small stacks that do not justify a dedicated container). That carve-out is described in [reference/docker-stacks](../reference/docker-stacks.md).

## What changes and what does not

The homelab grows. Services are added, retired, replaced; resources are tuned; new monitoring is wired up. The model above does not change. If it ever does, the change is significant enough to warrant rewriting this document, not patching it.
