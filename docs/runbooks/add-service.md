# Add a service

A service is added in lockstep across several layers of the repository, then applied through the runner. This runbook is the procedural walkthrough; for the model behind it, see [concepts/service-lifecycle](../concepts/service-lifecycle.md).

The same lockstep applies, in reverse, to removing a service. A short section at the end covers updates and removal.

## Decide before editing

Two decisions are worth making before touching any files.

**LXC or stack?** If the service warrants its own kernel and address — needs host networking, exclusive device access, or substantial resources — give it a dedicated LXC. If it is a small docker-compose unit that can share a host with similar services, make it a stack. The reasoning is in [reference/docker-stacks](../reference/docker-stacks.md).

**Pick a VMID.** Choose a free number in the appropriate range: low for infrastructure, middle for applications, high for runners. The number becomes the service's identity (its address, its hostname, its file name) for as long as the service exists; choose deliberately.

For a stack, no VMID is allocated — the stack inherits the host LXC's identity.

## The lockstep, for a new LXC

A new LXC service touches the following layers. All of them belong in one commit; partial commits leave the homelab in a half-deployed state.

1. **Container declaration.** Add a YAML file named after the new VMID, declaring the provisioning fields and the Ansible roles that should configure the container. The schema is in [reference/lxc-schema](../reference/lxc-schema.md).
2. **Configuration role, if needed.** If no existing role fits, add one under the roles directory, following the same layout as the others. Most services do not need a new role; they reuse base, the container runtime, and a service-specific or generic role.
3. **Internal DNS record.** Add a record in the internal discovery zone, mapping the service's hostname to the container's address. Without this, no other container can resolve the service by name.
4. **Reverse proxy entry**, if the service has a browser UI. Two coordinated edits are needed: an entry in the proxy's configuration that maps the service's friendly name to its backend address, and a record in the LAN-side proxy zone that points the friendly name at the proxy. See [concepts/reverse-proxy](../concepts/reverse-proxy.md) for what the proxy expects of a backend and which classes of service have known footguns.
5. **Monitoring scrape**, if the service exposes metrics. Add a scrape entry pointing the metrics collector at the service's address.
6. **CI matrix.** Add the new VMID to the deploy workflow's matrix so routine applies include it.
7. **Secrets**, if the service needs them. Add the credentials to the host's secrets directory in the same form as the others, and reference them from the role's variables or from a templated environment value in the relevant compose file.

Anything genuinely service-specific that an operator would need to know — credentials it needs, manual steps after first apply, idiosyncratic upstream behaviour — is captured either in the role's notes or in the [post-deploy-setup runbook](post-deploy-setup.md).

## The lockstep, for a stack on a shared host

A stack is lighter. The layers it touches:

1. **Stack definition.** Add a directory under the stacks root with a docker-compose definition and any supporting files. Templated environment values reference secrets that exist on the runner.
2. **Host LXC reference.** Edit the host LXC's configuration to list the new stack's identifier with state running. The next per-LXC configuration run on that host picks it up.
3. **Internal DNS, reverse proxy, monitoring, secrets** — same as for an LXC service, with the difference that the address points at the host LXC and the port is the one the stack publishes.

A stack does not get its own VMID, its own CI-matrix entry, or its own configuration role.

## Applying the changes

Once the lockstep edits are committed and pushed, the GitHub Actions workflow applies them. For the impatient, or when applying only one piece at a time, the runner's wrapper script offers per-control-plane operations: per-LXC provisioning, per-LXC configuration, DNS, hypervisor configuration. The order matters when applying by hand:

1. **Provisioning** first — the container has to exist before it can be configured.
2. **Configuration** second — once the container exists and is reachable.
3. **DNS** at any point after provisioning, since DNS records resolve to addresses that exist as soon as Terraform has assigned them.
4. **Reverse-proxy host configuration** after the new backend is configured and reachable, otherwise the proxy will return errors when it forwards.

Each operation is independently re-runnable. If something fails, fix it and run the relevant operation again; do not run them all back to back as a recovery.

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
2. **Stop the workload** — for a stack, set its state to removed in the host LXC's configuration and re-apply configuration; for an LXC, this step is implicit in the next.
3. **Destroy the container** — apply the per-LXC destroy. This is the irreversible step.
4. **Delete the YAML and any stack directory** as the final cleanup, after destruction succeeds.

If any step fails or reveals an unexpected dependency, the situation is recoverable until step three. Doing destruction first and discovering a forgotten reference afterwards is how a service ends up half-removed.
