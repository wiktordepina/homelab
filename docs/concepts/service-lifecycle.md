# Service lifecycle

A *service* in the homelab is an LXC container with a purpose, plus the supporting cross-cutting entries that make it discoverable, reachable, monitored, and deployable. A service exists when all of those exist; it does not exist when only some of them do.

This document describes the lifecycle abstractly. The concrete walkthrough for adding a service is in [runbooks/add-service](../runbooks/add-service.md).

## What "lockstep" means

Adding a service touches several artefacts in different layers of the repository. Skipping any of them produces a half-deployed service that may appear to work in isolation but breaks the operator's mental model and the system's invariants.

The recurring failure mode is: a container is provisioned and configured, a developer or operator can reach it by IP, and so the work *feels* complete — but the service has no DNS name, no proxy entry, no monitoring, and is not in the CI matrix. The next person to touch the homelab (often the same operator months later) finds inconsistent state and has to reconstruct the missing pieces.

The mitigation is a checklist that names every layer. The checklist is the runbook; the principle is that adding a service is *not* one change, it is several coordinated changes, and they belong in one commit.

## The layers a service touches

A new service typically requires changes across the following layers. Each is described conceptually here; the runbook gives the procedural detail.

**Container declaration.** A YAML file named after the new VMID, declaring the container's resources, mounts, and the Ansible roles that should configure it. This is the bridge between the two control planes; everything else either feeds into it or follows from it.

**Configuration role.** If the service needs anything beyond what a generic role provides (package install, configuration files, systemd units), a dedicated role is added. Roles follow the standard layout; conventions live in the project's role-authoring practice rather than in any one document.

**Internal DNS.** A record in the internal discovery zone, mapping the service's hostname to the container's address. Without this, no other container can find the service by name.

**LAN-side reverse proxy.** If the service has a UI intended for browser access, an entry in the proxy configuration and a corresponding record in the LAN-side proxy zone. Both are needed: the proxy needs to know which backend to forward to, and DNS needs to point the friendly name at the proxy.

**Monitoring.** If the service exposes metrics, a scrape entry pointing the metrics collector at it. If it does not, this layer is skipped.

**CI matrix.** The deploy workflow's matrix gains the new VMID so the service is included in routine applies.

**Documentation.** Anything non-obvious about the service — credentials it needs, post-deploy steps, integration quirks — is captured in the relevant runbook or role notes.

## Role ordering inside a container

Roles execute in the order they are listed in the container's YAML. A convention has emerged for application containers:

1. **Base setup** — system packages, time, hardening primitives common to every container.
2. **Container runtime**, if the service is a docker stack rather than a native install.
3. **Hardware drivers**, if the service needs them (typically GPU).
4. **Service-specific role(s)** — the actual purpose of the container.

The order matters: base sets up apt and timezone, the runtime depends on base, drivers may depend on the runtime (for the container toolkit), and the service depends on whatever it depends on. Inverting the order produces failures that look like role bugs but are ordering bugs.

## Variables and where they belong

Roles ship with sensible defaults. Container-specific overrides live at the call site in the container's YAML, alongside the role reference. Secrets are pulled from the runner's environment at apply time; see [secrets-and-state](secrets-and-state.md).

This keeps the role generic and the container's YAML the single source of "what does this container actually look like". A reader can answer "what is special about this container" by reading one file.

## Removal

Removing a service is the lockstep model in reverse. Cross-cutting references go first: removed from CI matrix, removed from monitoring, removed from the proxy, removed from DNS. Once nothing references the service, the container is destroyed via Terraform. The container's YAML is deleted last, after destruction succeeds.

Doing this in order matters because Terraform destruction is the irreversible step; the prior steps are reversible up until the moment the container goes away. If the destruction fails or reveals that something still depends on the service, the situation is recoverable. If the container is destroyed first, it is not.

## When a service is "done"

A service is done when:

- It is reachable by name on the internal zone.
- It is reachable through the proxy if it has a UI.
- It appears in monitoring if it exposes metrics.
- It is in the CI matrix and the next routine deploy includes it.
- Any post-deploy manual steps that cannot be expressed in IaC are recorded in the post-deploy runbook.

Anything less is not done; it is a half-deployed service waiting to confuse someone. The lockstep checklist exists to make this state unreachable.
