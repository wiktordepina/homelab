# Secrets and state

Two kinds of sensitive data live outside the repository: **secrets** (credentials the homelab needs to talk to upstream services) and **Terraform state** (the record of what infrastructure exists). Both are stored on the Proxmox host's persistent storage and made available exclusively to the GitHub Actions runner. Neither leaves the host.

This document explains the contract and the reasons for it.

## Where they live

Secrets are kept on the Proxmox host's storage in a dedicated directory, structured as a small set of shell scripts that export environment variables when sourced. Each script holds one logical credential or a tightly grouped set of related credentials.

Terraform state is kept on the same host, in a separate directory, with one state file per logical scope (per container for the per-LXC plans, plus a state file for the DNS plan). Splitting state by scope means an operation on one container cannot lock or corrupt the state of another.

Both directories are bind-mounted into the runner-toolbox container at runtime. Inside the container, scripts source the secrets directory and operate against the state directory as if they were local. Outside the container, on the host, they remain root-owned and isolated.

## Why they do not leave the host

The operator made a deliberate decision: credentials and state never get copied to a developer machine. The reasoning is twofold.

**Audit and accountability.** Every apply happens through CI, on a known machine, with a recorded log. There is no parallel history of "I ran this from my laptop" to reconstruct.

**Blast radius.** A laptop is portable, easily compromised, and routinely connected to networks that the homelab does not control. Confining credentials to the host means losing or compromising any other device does not compromise the homelab.

The cost is a slower local feedback loop: the operator pushes to a branch and waits for CI to apply, rather than applying directly. That cost is acknowledged and accepted. It is the system's most important security boundary and the one most worth defending against optimisation.

## The contract for new secrets

When a new service needs a credential, the operator:

1. Adds the secret to the host's secrets directory in the same shell-script form as the others.
2. References it from Ansible (via an environment lookup) or from Terraform (via a variable populated from the environment), depending on which control plane consumes it.
3. Documents what the secret is for, where it comes from upstream, and how it is rotated, in the relevant role or service notes.

The runner sources every secret script before invoking the toolbox, so any newly added secret is immediately available to subsequent runs. There is no central registry, no vault server, and no envelope encryption — just shell scripts on a hardened host. This is appropriate at this scale and would not be at a larger one.

## What happens when a secret is missing

A missing secret manifests as an empty environment variable. Ansible's environment lookup returns an empty string; Terraform's variable resolves to the type's zero value. Neither tool fails loudly by default. The result is usually a confusing downstream error — an authentication failure against an upstream service, a config file with a blank password, a TLS handshake with an empty token.

The mitigation is procedural rather than technical: the troubleshooting runbook lists "missing secret" as an early hypothesis when an apply produces unexpected authentication failures, and recommends inspecting the runner's environment as the first check.

## State and recovery

Terraform state is the source of truth for "what infrastructure exists according to the planner". If it is lost, Terraform's view of the world disappears, and the next apply will try to recreate everything (or, more dangerously, will create duplicates next to existing resources).

State is therefore treated as precious. It lives on persistent storage, on a pool with redundancy, on the same host that runs the runner. There is no off-host backup today; that is a known gap and a reasonable thing to fix when the cost of doing so falls below the cost of a state-loss incident. For now, the protection is "do not delete things on the host without thinking".

If state and reality drift — for example, after a manual change made on the Proxmox host outside of IaC — Terraform will detect the drift on the next plan. Reconciling it is a normal operation; details are in the troubleshooting runbook.
