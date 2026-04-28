# Troubleshooting

This runbook is a triage guide for common failure modes. It is organised by symptom rather than by component, since most failures are first noticed by what does not work rather than by what is broken.

For each symptom, the structure is the same: what the symptom looks like, the most likely causes in rough order of probability, and where to look first.

The runbook is deliberately not exhaustive. Failures specific to one service belong with that service's documentation; failures specific to one upstream tool are usually best diagnosed using that tool's documentation. What lives here is the homelab-shaped subset: the failures that arise from the homelab's particular shape and conventions.

## A new service is unreachable

A new service has been provisioned and configured, but trying to reach it fails. The cause is almost always a missing piece of the lockstep checklist; see [add-service](add-service.md).

**Reach by IP works, reach by name does not.** The internal DNS record was not added or DNS was not applied. Check the internal zone for the service's hostname; if it is missing, edit the zone file and apply DNS. If the record is there but resolution fails, the issue is on the resolver side rather than the records side.

**Reach by name works, reach via the proxy does not.** Either the proxy is not aware of the new backend, or the LAN-side proxy zone does not have a record for the friendly name, or both. Both edits are needed; either one alone is not enough.

**Reach via the proxy returns errors but the backend is up.** The backend may need to be told it is behind a proxy. Some services reject forwarded headers from unknown sources, or build absolute URLs from the wrong host. See [concepts/reverse-proxy](../concepts/reverse-proxy.md) for the trusted-proxies pattern.

**Live updates do not work.** Pages load but never refresh, real-time features do nothing, dashboards are frozen. The proxy is almost certainly not forwarding the protocol upgrade headers needed for WebSockets; this is configuration on the proxy itself, not on the backend. See the same concept doc.

## An apply fails with an authentication error

A Terraform or Ansible apply fails with an authentication-related error against an upstream service: Proxmox API rejection, DNS provider 401, registry pull failure, anything that looks like "the credential is wrong".

**The credential is missing.** A required environment variable is empty. The runner sources every script in `/pve/secrets/` before applying; if a new secret was added but its file is missing on the host, the variable is empty rather than absent and the failure is downstream. Check `/pve/secrets/` for a file containing the relevant credential.

**The credential is wrong.** The secret was added but the value is incorrect, has expired, or has insufficient scope. API tokens that look right but lack the necessary scope are a particularly common trap. Regenerate the credential with the right scope and update the secrets file.

**The credential has been rotated upstream without being updated locally.** Remote services occasionally rotate or revoke credentials. Confirm the credential is still valid by testing it directly against the upstream API; if it is not, replace it.

## Terraform reports state lock or unexpected drift

A Terraform apply fails because the state is locked, or because the plan shows changes nobody recently made through IaC.

**State is locked.** A previous apply was interrupted (process killed, runner rebooted, container stopped mid-run) and left the state lock in place. ZFS pool, host filesystem, or the runner's state mount may be involved. The remedy is to release the lock; do this only after confirming no other apply is genuinely running.

**Plan shows unexpected changes to a container.** Someone has changed the container's configuration on the Proxmox host outside of IaC, or the container's configuration has drifted because of a Proxmox upgrade. The plan is correct: it shows the difference between what IaC declares and what is currently true. Reconcile by either updating `config/lxc/<vmid>.yaml` to match reality or applying to make reality match the YAML.

**Plan shows recreation of an existing resource.** This is more serious. Either an attribute that requires recreation has changed, or the state has lost track of the resource and Terraform thinks it needs to create a new one alongside the existing instance. Recreations are sometimes intended (a hostname change, for example) and sometimes catastrophic (a resource being recreated and replacing the running instance). Read the plan carefully before applying and confirm intent.

## Ansible cannot reach a container

A configuration apply fails with an SSH or unreachable error.

**The container is not running.** Provisioning succeeded but the container is stopped, perhaps because of a host reboot. Start the container and retry.

**The container is running but the SSH service is not yet up.** Newly provisioned containers have a brief window where they are running but the SSH service has not finished starting. Wait and retry; if it persists, the configuration role for SSH did not run, and the issue is a chicken-and-egg case where the first apply needs to bootstrap SSH itself.

**The runner does not have an SSH key for the container.** Configuration apply expects a key to be available in the runner's mounted SSH directory (`~/.ssh` on the runner). If the directory is missing or empty, or the key has not been distributed to the container, configuration cannot connect.

**Network unreachable.** The runner cannot reach the container's address at all. Confirm the container's network attachment is correct and that the address matches `10.20.1.<vmid>`. The VMID-to-address mapping is rigid; a mismatch here means `config/lxc/<vmid>.yaml` or the actual network configuration has drifted.

## The runner is offline

GitHub reports the runner as offline; workflows queue but do not start.

**The runner container is stopped.** Start it through Proxmox.

**The runner service inside the container is not running.** Restart it. The runner installs as a system service; it should start on boot. If it does not, the install is broken and the runner role needs to re-apply.

**The runner is running but cannot reach GitHub.** A network problem between the homelab and GitHub. Confirm the runner can resolve and reach the upstream endpoints; this is rarely the cause but is worth ruling out.

**The runner's registration has been revoked or expired.** Re-registering with a fresh token fixes this; see [create-runner](create-runner.md).

## A workflow apply succeeded but the change is not live

The CI run is green, but the change does not appear to have taken effect.

**Only one of the relevant control planes was applied.** The workflow's matrix includes the layers that were edited, but if a cross-cutting layer was edited (DNS, reverse proxy, monitoring) and the workflow does not include it, the change committed without being applied. Check the workflow definition against the layers that were edited in the commit.

**The change was applied but caching is in the way.** Browser caches and DNS caches both routinely conceal a successful change. A hard reload, a new browser session, or waiting for the relevant TTL to expire usually clears it. If the homelab's internal resolver is itself caching aggressively, reduce the record's TTL for the next change cycle.

**The applied state is correct but a downstream service has not picked it up.** Some services reload only on signal, restart, or schedule. A reverse proxy reload after a configuration edit, a service restart after a configuration file change, a metrics collector reload after a scrape change: these may need to be triggered explicitly and may be missing from the configuration role. The fix is in the role, not in the apply.

## When in doubt

A surprising number of homelab failures resolve to one of two root causes: a missing piece of the lockstep checklist, or a missing secret in `/pve/secrets/`. When triage gets stuck, walk through the [add-service](add-service.md) lockstep against the service in question, and inspect the runner's environment for the secrets the apply expects. One of the two will usually surface the problem.

If the problem is not in either, suspect drift between IaC and reality (something changed by hand on the host) and run a plan against the relevant control planes to surface it. Drift hides the truth in plain sight: the apply succeeds, but it is not applying the thing you think it is.
