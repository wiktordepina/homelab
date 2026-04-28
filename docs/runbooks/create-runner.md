# Create a GitHub Actions runner

This runbook covers provisioning an additional self-hosted runner for the repository. The first runner — the one that bootstraps the homelab from scratch — is out of scope for this documentation; that work belongs to the separately scoped bootstrap exercise referenced in [ARCHITECTURE](../ARCHITECTURE.md).

In the steady state, additional runners are added to the homelab the same way any other service is added (see [add-service](add-service.md)), with the runner-specific manual steps below. The runner is itself an LXC container in the high VMID range.

## Why an additional runner

One runner suffices for routine workload. Reasons to add a second include:

- **Self-update.** The same runner cannot apply changes that take itself offline (image rebuild, reboot, kernel update). A second runner unblocks those operations.
- **Capacity.** Concurrent jobs queue if there is only one runner. A second runner reduces that queue when applies overlap.
- **Isolation.** Some workloads benefit from running on a runner that does not share state with the production runner.

If none of these applies, do not add a runner.

## What is in IaC and what is not

The runner's *container* is provisioned by IaC like any other LXC: it has a YAML file in the configuration directory, a base role plus the runner role, and entries in the relevant cross-cutting layers (DNS does not apply, reverse proxy does not apply, monitoring optionally applies).

The runner's *registration with GitHub* — pairing the runner with the repository using a one-time token issued by GitHub — is intentionally manual. The token is short-lived and operator-bound; baking it into IaC would require leaking a privileged credential into automation that does not need it.

The split is therefore: IaC creates the container and prepares the environment, the operator pastes a registration token into the running container the first time.

## Procedure

The procedure has three phases.

### 1. Provision the container

Add a YAML file for the new VMID in the runner range, declaring the container with the resources it needs and listing the runner role under the Ansible configuration. The container needs the same persistent mounts every runner needs: the host's secrets directory and the host's Terraform state directory. These mounts are what makes the runner an apply-capable machine; without them it can do nothing useful.

Apply per-LXC provisioning followed by per-LXC configuration through the wrapper. After this phase, the container exists, has the toolchain installed, and can build the toolbox image, but does not yet appear in GitHub as an available runner.

### 2. Register with GitHub

Generate a one-time runner registration token from GitHub's repository settings. Tokens expire quickly; generate the token immediately before this step, not in advance.

In a shell on the new runner container, run the registration step provided by GitHub's runner installer, supplying the token. The registration writes a configuration file inside the container and installs a service that starts on boot.

After registration, the runner appears in GitHub's runner list. Note that the registration is per-runner-instance: destroying the container removes the runner from GitHub on the next housekeeping pass, but a clean removal involves de-registering before destroying. See "Removing a runner" below.

### 3. Build the toolbox image

The runner cannot apply anything until it has the toolbox image. The lint operation builds it on first run; alternatively, build it explicitly. Subsequent applies reuse the existing image until the toolbox sources change.

After this phase, the runner is ready to pick up jobs.

## Updating the runner software

The runner software is installed inside the container by the runner role. Updating to a new version is a configuration change: bump the version pinned by the role, then re-apply per-LXC configuration. The role handles stopping the service, swapping the binaries, and starting the service again.

Operators should not update the runner by hand inside the container. Manual updates produce drift that the next configuration apply will partially undo and partially leave alone, in confusing combinations.

## Removing a runner

Reverse the steps:

1. From GitHub's runner list, remove the runner. This is a graceful de-registration; the runner stops accepting new jobs.
2. Wait for any in-flight job to finish.
3. Destroy the container through the per-LXC destroy operation, and delete the YAML file.

Removing the container before de-registering leaves an orphan entry in GitHub's runner list, which has to be cleaned up by hand.

## Verifying the runner is healthy

A runner is healthy when:

- It appears as **idle** in GitHub's runner list when no job is queued.
- A trivial workflow run (a no-op job dispatched manually) completes on it.
- The lint operation completes locally on the runner, confirming the toolbox image builds and runs.

Anything less means there is a misconfiguration to chase; the [troubleshooting runbook](troubleshooting.md) covers the common causes.
