# Post-deploy service setup

This runbook records the manual steps that have to happen *after* a service has been provisioned and configured by IaC, before the service is fully usable. It exists because some configuration cannot — or should not — be expressed as code in this repository.

If a step here can reasonably be moved into IaC, it should be. Treat the contents of this document as a backlog of automation candidates as much as a procedural reference.

## What belongs here

A manual step belongs in this document when at least one of the following is true:

- **The service owns its own configuration at runtime.** Some services persist their configuration in files they manage themselves (writing to disk in response to UI actions). Templating those files from Ansible would clobber the service's own writes on the next apply. The right answer is to do the initial configuration through the service's UI and document it.
- **Onboarding requires an interactive flow.** Account creation, owner setup, location and time zone selection, an admin password set in the UI: these are first-run flows that have no IaC equivalent.
- **A secret is generated through the service's UI.** Long-lived API tokens and similar credentials are issued through web UIs and shown only once. Capturing the value and storing it in the homelab's secrets requires a human in the loop.
- **An integration requires user interaction at the device.** Pairing a hub, pressing a physical link button, scanning a QR code — these cannot be automated regardless of how thorough the IaC is.

A manual step does **not** belong here when it could be expressed as a role variable, a template, or a one-time task in a configuration role. Those are bugs to fix, not entries to document.

## Format for new entries

Each service's section should be self-contained. The header identifies the service and the container it runs in. The body lists steps in order, with each step naming what it does, why it cannot be automated, and what you need to do.

Steps that are deferred — known to be needed eventually but not done yet (for example, wiring monitoring once the service has a stable token) — are marked as such with a note about what triggers them. The codeowner prefers explicit deferral over silent skipping: "we will do this later" is a useful operational state.

Steps that are *automation candidates* — things that *could* be in IaC with effort but the codeowner has not yet committed to — are marked as such, so the document also functions as a backlog.

## Worked example: home assistant

This section is the canonical example of the format. It is also the only entry currently needed; new entries follow the same structure.

### What the service is

Home Assistant runs as a docker container deployed via the `containers` Ansible role from the stack at `config/docker/homeassistant/`, in a dedicated LXC (206) at `10.20.1.206`. It uses host networking so that local-discovery protocols work for device pairing.

### After IaC succeeds

**Initial onboarding is interactive.** On first reach, the service presents a one-time wizard that creates the owner account and asks for location, time zone, and unit system. Skip the integration auto-discovery step until after the trusted-proxies configuration is in place; otherwise integrations bind to the wrong external URL and have to be re-paired.

**The reverse proxy must be declared as a trusted proxy.** Until the service knows it is behind the proxy, it rejects forwarded headers and returns errors when reached through the proxy hostname. This is a configuration concern that lives in the service's own configuration file. Add the proxy's address to the service's trusted-proxies list and enable the use of the forwarded-for header. Restart the service afterwards.

This is *not an automation candidate* because the service writes to its own configuration file at runtime; templating it from IaC would fight with the UI's own edits. The right fix in the long run is to use the service's environment-variable equivalent of the same setting, if upstream supports one.

**Local-discovery integrations require interaction at the device.** Pairing the lighting hub, for example, requires pressing a physical button on the hub during pairing, in response to a UI prompt. There is no IaC equivalent.

**A long-lived access token is needed for monitoring.** Generating the token is an interactive flow in the service's UI; the token is shown only once. The token is then stored in the homelab's secrets and referenced from the monitoring scrape configuration. This is *deferred* until monitoring is wired up, and is an *automation candidate* if upstream ever offers a non-interactive way to mint a service token.

**Public exposure** through the public-zone tunnel is an additional manual step on the tunnel side. It is currently configured by hand in the public DNS provider's dashboard and is the same kind of manual carve-out as every other public route. See [concepts/domains-and-tls](../concepts/domains-and-tls.md) for context. This step is deferred and is an automation candidate when the tunnel routing itself moves into IaC.

## Adding a new entry

When provisioning a new service that has manual setup, add a section under this runbook using the same shape as the worked example: what the service is, then a numbered or bulleted list of post-deploy steps. For each step, name what cannot be automated and why; this both helps whoever performs the procedure next and identifies which steps are temporary versus inherent.

Cross-link to this runbook from the relevant role's notes and from any reference document that introduces the service, so the manual steps are discoverable from the places where someone first encounters the service.
