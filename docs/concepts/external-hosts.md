# External hosts

Almost every workload in the homelab is an LXC container on the Proxmox host, declared and reconciled by the two control planes that own the LXC fleet. A small number of workloads cannot fit that model, because they need hardware the Proxmox host does not have or cannot expose meaningfully: a Bluetooth radio, GPIO pins, USB peripherals tied to a particular physical location, sensors and actuators wired into the room they observe.

These workloads run on *external hosts* — physical machines outside the Proxmox host that this repository still configures, just through a thinner control plane than the LXC fleet uses. This document explains why the carve-out exists, what the homelab manages on those hosts and what it does not, and how an external host differs from an LXC in the operator's mental model.

For the schema describing an individual external host, see [reference/external-host-schema](../reference/external-host-schema.md). For the procedural walkthrough of adding one, see [runbooks/add-external-host](../runbooks/add-external-host.md).

## Why the carve-out exists

The homelab's first principle is that VMID is identity: every service is an LXC, and the container ID determines its address, its hostname, and its place in the operator's model. That principle assumes the Proxmox host can host the workload. When it cannot — because the workload depends on hardware that is not present in or sensibly attachable to the Proxmox host — the alternative is a separate physical machine.

The codeowner could in principle add the missing hardware to the Proxmox host (a Bluetooth dongle, a GPIO breakout) and use device passthrough to expose it to a container. That would preserve the VMID-as-identity model but at the cost of introducing fragile device-passthrough configuration to the hypervisor for the sake of a single container. For workloads that are unambiguously edge-shaped — radios, room-local sensors, things with cables that run to physical objects — a small dedicated machine is operationally simpler and cheaper to reason about.

External hosts are therefore an acknowledged exception to the LXC-fleet model, not an oversight. They exist because some workloads belong on hardware that is not the hypervisor.

## What the homelab manages on an external host

The same configuration control plane that converges an LXC also converges an external host: roles from the Ansible role library, applied in order, against an inventory entry for that host. A role written for an LXC works on an external host without modification, provided its assumptions about the operating system are met.

What the repository does *not* own for an external host is the steps that bring the machine into existence in the first place. The operating system is installed by hand. The network configuration that gives the host its address is set by hand. The SSH keys that allow the runner to reach the host are placed by hand. These steps happen once, when the machine is unboxed; the repository takes over from the moment the machine is reachable and the runner's key is authorised.

This is a deliberate split. The provisioning control plane that the LXC fleet uses (Terraform against Proxmox) does not generalise to bare metal — there is no API for "create a Raspberry Pi" the way there is one for "create an LXC". Trying to express bare-metal installation in IaC for a fleet of one or two machines is more bureaucracy than benefit. The repository instead documents the manual-bootstrap requirement and assumes it is met before configuration runs.

## Identity without a VMID

An LXC's identity is its VMID, which is the integer the hypervisor assigns and from which everything else (address, hostname, file name) is derived. An external host has no VMID; nothing in this repository assigns it one. Identity is the hostname, chosen by the operator, used as the file name of the host's declaration, and reflected in the DNS record that points at its address.

Because there is no VMID, there is no implicit address either. The external host's address is whatever the operator configured by hand when bringing the machine up; the repository records it as a fact, not as something derivable from identity. This is the practical difference: for an LXC, you choose a VMID and the rest follows; for an external host, you record the address you already gave it.

The naming convention is open and a matter of operator preference. The codeowner's habit is to name external hosts by their physical form factor with a numeric suffix, so that the directory listing reads as a fleet rather than a list of one-off machines.

## Cross-cutting concerns

External hosts participate in most cross-cutting concerns the same way LXCs do.

**Internal DNS.** An external host is given a record on the internal discovery zone, the same way an LXC is. Other containers reach it by the same kind of name they would use for any other host. The DNS control plane does not care whether the address it is publishing belongs to an LXC or to a Raspberry Pi.

**Reverse proxy.** If an external host exposes a UI intended for browser access, the same proxy entry pattern applies: a backend address in the proxy configuration and a record in the LAN-side proxy zone pointing at the proxy. The proxy treats the external host as just another upstream.

**Monitoring.** The metrics collector scrapes external hosts the same way it scrapes LXCs, given a target address.

**CI matrix.** The deploy workflow has an analogous slot for external hosts, kept separate from the LXC matrix because the operations applied to them are different (configuration only, no provisioning).

The only cross-cutting concern that does not apply is provisioning. There is no Terraform plan to apply for an external host, because the repository does not provision the machine. Everything else looks the same.

## Why external hosts are a carve-out and not the default

The LXC fleet model is the right answer for the vast majority of workloads. LXCs are cheap to create, cheap to destroy, and live entirely inside the operator's mental model of "things on the Proxmox host". External hosts come with costs the LXC fleet does not have:

- A separate physical machine to keep alive, with its own power supply, its own storage, its own update cadence, and its own failure modes that the codeowner has to learn.
- Manual bootstrap that bypasses the IaC discipline the rest of the homelab maintains.
- A second deployment model in CI, with its own workflow and its own moving parts to keep working.

The model is therefore not a recommendation to spread workloads across many machines. It is an acknowledgement that some workloads cannot live on the hypervisor, and a way to keep their configuration in the same repository and under the same conventions as everything else. When in doubt, the answer is an LXC; an external host is reached for when the hardware leaves no other choice.
