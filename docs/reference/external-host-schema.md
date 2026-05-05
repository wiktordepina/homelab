# External-host schema

Each external host is fully described by one YAML file at `config/external-hosts/<hostname>.yml`, named after the host's chosen hostname with no exceptions. The file is consumed by the external-host configuration control plane (Ansible only) and is the single source of truth for "what is this external host".

This document describes the schema. For the rationale behind the model, see [concepts/external-hosts](../concepts/external-hosts.md). For the procedural walkthrough of using it, see [runbooks/add-external-host](../runbooks/add-external-host.md).

## Top-level shape

An external-host file has up to four top-level sections:

- An **identity** section, declaring the hostname, fully-qualified name on the internal zone, target address, and the SSH user the runner connects as.
- A **manually-provisioned** section, listing what the operator did by hand before this repository took over. This is documentary, not enforced.
- A **configuration** section, consumed by Ansible, declaring the roles to apply against the host.
- An optional **notes** section, free-form prose for anything that would be useful to a future reader.

The top-level keys are `identity:`, `manually_provisioned:`, `ansible:`, and `notes:`. A file with only the identity section is well-formed but rarely useful — the host is named but no configuration is applied to it.

## Identity fields

The identity section names the host on the network. The required fields express the hostname (used as the file name, the inventory key, and the short DNS record), the FQDN on the internal discovery zone, the target IP address, and the SSH user the runner uses.

Two conventions are worth knowing:

- The hostname has no implicit address, unlike an LXC where the address is derived from the VMID. The address is whatever the operator configured by hand when bringing the machine up; the repository records it.
- The SSH user is typically `root` for headless single-purpose machines like a Raspberry Pi running one or two daemons. A non-root user with `sudo` is also acceptable and pushes the same role library through unchanged, provided the role's tasks declare `become: true` where they need privilege.

## Manually-provisioned section

The manually-provisioned section is a short list of facts about what the operator did before this repository started managing the host. The recurring entries are the operating system installation, the network configuration that gave the host its address, and the SSH authorised-keys entry that lets the runner in.

This section is documentary. The repository does not validate it, does not converge it, and does not detect when it drifts. Its purpose is to make the manual-bootstrap requirement visible at the file where the host is declared, so that anyone reading the file can answer "what do I need to do by hand if this machine has to be replaced".

When a manually-provisioned aspect is later moved into IaC, the corresponding entry is removed from this list.

## Configuration section

The configuration section, under the `ansible:` key, has the same shape as the configuration section of an LXC file. It declares the roles to apply (resolved against `ansible/roles/<name>/`), in order, with optional per-role variable overrides.

The same conventions apply: roles execute in the order listed, the codeowner's role-ordering convention holds (base setup, then any runtime, then service-specific roles), and secrets are pulled from the runner's environment at apply time using `lookup('ansible.builtin.env', '<NAME>')`.

A role written for an LXC works against an external host without modification, provided the role's assumptions about the operating system are met. The configuration control plane does not distinguish between the two targets.

## Notes section

The notes section is free-form prose attached to the host. The codeowner's convention is to record anything a future reader would want to know that is not captured by the structured fields: physical location of the machine, what hardware it carries, why it exists outside the LXC fleet.

This section is not interpreted by any tooling; it exists to keep context next to the declaration.

## What the schema does not describe

The schema describes an external host at rest: what it is, where it lives on the network, what configuration it should converge to. It does not describe operational state, runtime metrics, or the physical machine itself beyond what the operator chose to record in the notes.

A host file is not a complete description of a *service* running on the host. If a daemon on the host exposes a UI, has a DNS record on the internal zone, or appears in monitoring, those entries live in their own files (the same way they do for LXC services) and are linked to the host through the hostname-as-identity convention.
