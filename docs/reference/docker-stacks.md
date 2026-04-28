# Docker stacks

A *docker stack* in this homelab is a docker-compose definition that runs inside an LXC container, alongside whatever other stacks share that container. Stacks are an alternative to dedicating an LXC to one service: cheaper to add, harder to isolate, appropriate for a specific class of services.

This document covers the conventions. For when to choose a stack rather than a dedicated LXC, see the decision below.

## When to choose a stack rather than a dedicated LXC

The codeowner's default is a dedicated LXC. A stack is appropriate when the candidate service is small enough that giving it its own kernel, network stack, and file system would be overkill, and when its operational needs are similar enough to existing stacks that it can share a host without surprise.

Specifically, a stack is a good fit when:

- The service is a single docker-compose unit with modest resource needs.
- It does not need its own IP address; the host LXC's address is sufficient.
- It does not require host-level features that conflict with cohabiting (host networking on a shared host, exclusive device access).
- It does not need its own kernel or its own systemd.

A dedicated LXC is the right choice when:

- The service needs host networking and discovery protocols (mDNS, SSDP) that do not survive being inside a docker network.
- The service needs exclusive access to a hardware device.
- The service has security or reliability properties that warrant isolation from the rest.
- The service is large enough that its resource footprint dominates the host.

The current home assistant deployment is a worked example: it is a docker stack but lives in its own dedicated LXC because it needs host networking for device discovery and would conflict with anything else.

## Where stacks live

Stack definitions live under `config/docker/`, one subdirectory per stack, with the subdirectory name acting as the stack's identifier. Each `config/docker/<name>/` holds a `docker-compose.yaml` and any supporting files (templates, init scripts, environment file fragments).

A host LXC opts into running a stack by listing the stack's identifier in its `config/lxc/<vmid>.yaml` under the `containers:` variable of the `containers` Ansible role, alongside a desired state (`up`, `down`, or `destroyed`). The `containers` role reads that list, copies the stack's `config/docker/<name>/` directory into the container, and reconciles it against the desired state.

This means a stack is not "deployed" by editing `config/docker/<name>/` alone. It is deployed by also referencing it from a host LXC. A stack with no host listing is dormant code; a host listing referencing a non-existent stack is an error caught at apply time.

## How stacks reach secrets

Docker compose files under `config/docker/` support templating for environment values via `{{ lookup('ansible.builtin.env', '<NAME>') }}`, evaluated by Ansible at apply time using the runner's environment. A stack that needs a credential references it as a templated value, and the value is filled in from the relevant script in `/pve/secrets/`. Nothing is hard-coded into compose files.

The contract is: every templated value resolves at apply time. A missing environment variable produces an empty value, which usually breaks the stack at runtime in ways that look like service bugs. The troubleshooting runbook lists this as an early hypothesis.

## Adding a stack

Adding a stack involves two coordinated changes. Either change alone leaves the stack in a non-functional state.

1. **Define the stack** by adding a directory under `config/docker/<name>/`, with a `docker-compose.yaml` and any supporting files. Templated environment values reference secrets that exist in `/pve/secrets/` on the runner.
2. **Reference it from a host LXC** by adding the stack's identifier to that LXC's `containers:` list in `config/lxc/<vmid>.yaml`, with the appropriate desired state.

The next `ansible_lxc <vmid>` on the host LXC picks up the new reference and deploys the stack. There is no separate stacks-only operation.

## Lifecycle states

A stack reference in a host LXC's `containers:` list carries a desired state. The states that matter are:

- **`up`** — the stack should be present and its services running.
- **`down`** — the stack should be present but its services stopped.
- **`destroyed`** — the stack's containers and ancillary docker objects should be gone.

Removing the reference from the host LXC's configuration is *not* the same as setting state to `destroyed`: a reference with no state, or no reference at all, leaves whatever is currently running untouched. To clean up properly, set state to `destroyed` first, re-run configuration, then drop the reference.

This is verbose but explicit, and matches how the rest of the homelab approaches removal: tear down references in order before deleting the underlying thing.

## Constraints on a shared host

Stacks on a shared host cohabit, which imposes constraints worth being explicit about:

- **Port conflicts** are real. Two stacks cannot both bind the host port 8080.
- **Volume names** are docker-namespace-shared. Stacks should prefix volumes with the stack identifier to avoid collisions.
- **Network names** are similarly shared. Each stack should declare its own networks.
- **Restart-loops in one stack** consume resources that other stacks need; a misbehaving stack on a shared host is everyone's problem.

When any of these become recurring sources of friction, the right move is to promote the offending stack to its own LXC.
