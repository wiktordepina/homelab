# Runner model

The homelab has one execution surface for applies: a self-hosted GitHub Actions runner running in an LXC container on the same Proxmox host it manages. This document explains why the runner exists in this shape and what consequences follow.

## The runner is the only place applies happen

Every operation that mutates the homelab — Terraform applies against Proxmox, Ansible runs against containers, DNS updates, certificate operations — happens on the runner, inside a purpose-built container image (the *toolbox*). Nothing applies from a developer machine. This is the single most important fact about the model and the rest of this document follows from it.

The reasons are covered in [secrets-and-state](secrets-and-state.md): credentials and Terraform state live only on the host, mounted only into the runner. Anywhere else, applies simply cannot work because the inputs are not there.

## The toolbox image

The toolbox is a single container image that bundles every tool the homelab needs: Terraform with its custom provider, Ansible with the required collections, the linting tools, and the small wrapper scripts (`runner-toolbox/scripts/`) that compose them into the four control-plane operations.

The image is built on the runner itself, from the `runner-toolbox/` sources in this repository. The codeowner deliberately does not push it to a registry. The reasons:

- **No public attack surface.** The image contains nothing secret, but publishing it would invite questions about supply-chain trust that the homelab does not need to answer.
- **No version drift.** The image that built last week does not need to be hunted down. A fresh build from the current commit is always the right artefact.
- **No registry dependency.** The homelab can apply changes without depending on any external service beyond GitHub itself.

A consequence is that the first thing a brand-new runner does is build the image. After that, builds are incremental and triggered by changes to the toolbox sources.

## The lint-versus-apply split

There is a sharp line between operations that need state and secrets and operations that do not.

**Lint** (invoked via `./run/lint`) is read-only: it parses YAML, validates Terraform syntax, runs the Ansible playbook syntax checker, and checks formatting. It needs neither secrets nor state, only the source tree. It runs on a developer machine (against a locally built toolbox image) and on every CI push via `.github/workflows/lint.yml`. It is fast, safe, and deliberately the only thing developers have access to locally.

**Apply** (invoked via `./run/execute_runner`) is mutating: it reaches out to Proxmox, opens SSH connections to containers, writes Terraform state, talks to upstream APIs. It needs secrets and state, so it runs only on the runner.

The split is the codeowner's answer to "how do I get a fast feedback loop without copying credentials to my laptop". The answer is: lint locally as often as you like, push when ready, and accept the round-trip through CI for applies.

## How an apply is composed

When the runner applies changes, it runs a workflow that invokes one or more of the four control-plane operations described in [architecture](architecture.md): per-LXC provisioning (`terraform_lxc`), per-LXC configuration (`ansible_lxc`), DNS (`terraform_dns`), host configuration (`ansible_pve`). Each is a small wrapper script under `runner-toolbox/scripts/` that pulls the relevant inputs from the per-container YAML or its equivalent, runs the right tool against the right state file, and returns a status.

There is no orchestrator that runs the four together. Lockstep across them is your responsibility when applying by hand, guided by the workflow definitions in `.github/workflows/` and the [add-service runbook](../runbooks/add-service.md). This is a deliberate choice by the codeowner: each operation is comprehensible on its own, and you stay in control of the order.

## Why one runner is enough

A single runner is sufficient because applies are not frequent and because the homelab is a single host. Running the runner on the same host it manages is operationally convenient but creates a chicken-and-egg problem when the host or runner itself needs work: the same runner cannot apply changes that take it offline. The codeowner accepts this limitation, addressed by a small number of operations that have to be run by hand on the host (the runner runbook covers them) and by the option to spin up an additional runner in the `500–599` VMID range when needed.
