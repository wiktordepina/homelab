# Runner model

The homelab has one execution surface for applies: a self-hosted GitHub Actions runner running in an LXC container on the same Proxmox host it manages. This document explains why the runner exists in this shape and what consequences follow.

## The runner is the only place applies happen

Every operation that mutates the homelab — Terraform applies against Proxmox, Ansible runs against containers, DNS updates, certificate operations — happens on the runner, inside a purpose-built container image (the *toolbox*). Nothing applies from a developer machine. This is the single most important fact about the model and the rest of this document follows from it.

The reasons are covered in [secrets-and-state](secrets-and-state.md): credentials and Terraform state live only on the host, mounted only into the runner. Anywhere else, applies simply cannot work because the inputs are not there.

## Where apply runners come from

There is one exception to that rule, and it is the runner itself. An apply runner cannot be provisioned by the process it hosts. The first one has nothing to provision it. After that, a job reshaping the container it runs in can destroy or restart the machine underneath itself, and the provisioning tooling would happily plan exactly that. So the ordinary provisioning and configuration operations refuse apply runners outright. Instead, apply runners are created and re-configured by a small bootstrap run from a developer machine, which drives the hypervisor directly and configures the new container from the inside.

The exception is kept narrow on purpose. The bootstrap carries no secrets and no state: those stay on the host and reach a runner only through its mounts, exactly as before. The only credential passing through the developer machine is the one-time registration token the forge issues to a human. There is still one definition of what a runner *is*. The bootstrap applies the same configuration code everything else uses; it contributes only the steps no runner can do for itself. And because an apply runner holds nothing of its own, rebuilding one is cheap, which in turn keeps the bootstrap exercised rather than left to rot until the day it is needed.

The distinction from CI runners is deliberate as well. They hold no credentials, so provisioning them from a job risks nothing, and they go through the ordinary path like any other container.

## The toolbox image

The toolbox is a single container image that bundles every tool the homelab needs: Terraform, Ansible with the required collections, the linting tools, and the small wrapper scripts (`runner-toolbox/scripts/`) that compose them into the four control-plane operations.

The image is built on the runner itself, from the `runner-toolbox/` sources in this repository. The codeowner deliberately does not push it to a registry. The reasons:

- **No public attack surface.** The image contains nothing secret, but publishing it would invite questions about supply-chain trust that the homelab does not need to answer.
- **No version drift.** The image that built last week does not need to be hunted down. A fresh build from the current commit is always the right artefact.
- **No registry dependency.** The homelab can apply changes without depending on any external service beyond GitHub itself.

The image a job runs is always the one built from the commit it is applying. Each runner builds it the first time a job needs it, and keeps it until the toolbox sources change. With more than one runner, none of them can be left on an older toolbox than the others, and an apply can never race a rebuild. The cost is that the first job on a new runner, and the first after each toolbox change, waits for a build.

## The lint-versus-apply split

There is a sharp line between operations that need state and secrets and operations that do not.

**Lint** (invoked via `./run/lint`) is read-only: it parses YAML, validates Terraform syntax, runs the Ansible playbook syntax checker, and checks formatting. It needs neither secrets nor state, only the source tree. It runs on a developer machine (against a locally built toolbox image) and on every CI push via `.github/workflows/lint.yml`, where it uses a GitHub-hosted runner rather than the apply runner: a pushed branch should never execute code on the machine that holds the secrets. It is fast, safe, and deliberately the only thing developers have access to locally.

**Apply** (invoked via `./run/execute_runner`) is mutating: it reaches out to Proxmox, opens SSH connections to containers, writes Terraform state, talks to upstream APIs. It needs secrets and state, so it runs only on the runner.

The split is the codeowner's answer to "how do I get a fast feedback loop without copying credentials to my laptop". The answer is: lint locally as often as you like, push when ready, and accept the round-trip through CI for applies.

## How an apply is composed

When the runner applies changes, it runs a workflow that invokes one or more of the four control-plane operations described in [architecture](architecture.md): per-LXC provisioning (`terraform_lxc`), per-LXC configuration (`ansible_lxc`), DNS (`terraform_dns`), host configuration (`ansible_pve`). Each is a small wrapper script under `runner-toolbox/scripts/` that pulls the relevant inputs from the per-container YAML or its equivalent, runs the right tool against the right state file, and returns a status.

There is no orchestrator that runs the four together. Lockstep across them is your responsibility when applying by hand, guided by the workflow definitions in `.github/workflows/` and the [add-service runbook](../runbooks/add-service.md). This is a deliberate choice by the codeowner: each operation is comprehensible on its own, and you stay in control of the order.

## Why one runner is enough

A single runner is sufficient because applies are not frequent and because the homelab is a single host. Running the runner on the same host it manages is operationally convenient but creates a chicken-and-egg problem when the host or runner itself needs work: the same runner cannot apply changes that take it offline. The codeowner accepts this limitation, addressed by a small number of operations that have to be run by hand on the host (the runner runbook covers them) and by the option to spin up an additional apply runner in the `600–699` VMID range when needed.
