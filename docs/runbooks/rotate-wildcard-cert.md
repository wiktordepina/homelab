# Rotate the wildcard SSL certificate

The LAN-side reverse proxy (LXC 110, `nginx`) terminates TLS for `*.homelab.matagoth.com` using a wildcard certificate. The certificate is issued by Let's Encrypt over a DNS-01 challenge against Cloudflare, and renewed automatically by certbot running on the proxy container.

This runbook covers what to do when **automatic renewal stops working** — either silently, when the certificate is approaching expiry without having been renewed, or noisily, when a renewal attempt has produced an error. Routine operation needs no manual intervention.

For the design context — which zone this certificate covers, why TLS terminates only at the proxy, the relationship to the public zone — see [concepts/domains-and-tls](../concepts/domains-and-tls.md).

## Pre-conditions

The certificate-renewal mechanism is wired up by the `certbot` and `nginx_reverse_proxy` Ansible roles when LXC 110 is configured. If LXC 110 has been provisioned but configuration has not run successfully, this runbook does not apply yet; run `ansible_lxc 110` first.

The renewal mechanism uses a Cloudflare API token for the DNS-01 challenge against the public zone. The token is one of the homelab's secrets, lives in `/pve/secrets/` on the host, and is mounted into the runner. If renewal is failing because of a credential problem, the fix is to refresh the token there, not to change anything inside the proxy container.

## Diagnose first

The most useful first step is to confirm the failure mode. Three states are possible.

**Renewal succeeded recently and the certificate is fresh.** Check the certificate's expiry; if it is months away, the system is healthy and there is nothing to do.

**Renewal is failing repeatedly.** Certbot logs the failures. Inspect the recent certbot logs on LXC 110 for the error class — DNS propagation timeout, rate limit, credential rejection, account problem — and address that specific cause.

**Renewal has not been attempted.** The renewal systemd timer is not running, or has been disabled. Check the timer's status on LXC 110; re-enable it if needed (or, more reliably, re-run `ansible_lxc 110` to restore it from the role).

Each of these has a different remedy; running the renewal manually without diagnosing first wastes a renewal attempt against the rate-limited issuer.

## Common remedies

### DNS propagation timeout

Certbot provisions a temporary `_acme-challenge` TXT record for the challenge and waits for it to propagate before asking Let's Encrypt to verify. Slow propagation occasionally causes timeouts. Re-running with a longer `--dns-cloudflare-propagation-seconds` value usually succeeds. This is a transient failure mode and rarely recurs; if it recurs, the problem is more likely with Cloudflare than with the homelab.

### Credential rejection

If certbot cannot create the challenge record, the Cloudflare token is wrong, expired, or insufficiently scoped. Generate a fresh token in the Cloudflare dashboard with the right scope, update `/pve/secrets/cloudflare.sh`, re-run `ansible_lxc 110` to push the credential file into the container, and re-run renewal. Insufficient scope is a recurring trap: the token needs both **Zone → Zone → Read** and **Zone → DNS → Edit** on the public zone (`matagoth.com`).

### Rate limit

Let's Encrypt enforces both per-domain and per-account rate limits. If a recent batch of failed renewals exhausted the allowance, no further renewal will succeed for some time. The remedy is to wait; in the interim, the existing certificate is still valid. Use the `--staging` flag when iterating on a fix that requires repeated attempts.

### Disabled or removed timer

If automation has been turned off — sometimes inadvertently, sometimes by a previous troubleshooting session — re-running `ansible_lxc 110` re-installs the renewal timer. Manual edits inside the container drift away the next time configuration runs anyway, so this is usually the right fix.

## Triggering a renewal manually

When automation is healthy but a renewal needs to happen *now* — for example, immediately after rotating the Cloudflare token, to confirm everything works — invoke certbot directly on LXC 110 with its renewal command. A successful manual run also reloads nginx so the new certificate is picked up without a process restart; if it does not, reload nginx by hand afterwards.

Use the `--staging` flag for any manual run that is not certain to succeed. A manual production run that fails counts against the rate limit.

## After rotation

After a successful renewal:

- Confirm the new certificate's expiry has moved forward by inspecting the certificate from a client that talks to the proxy.
- Confirm nginx is serving the new certificate; certbot's deploy hook should have reloaded nginx automatically.
- Confirm at least one backend still resolves end-to-end through the proxy by hitting it from a browser.

If automation was the failure mode (timer disabled, hook missing), the next thing to do is to re-run `ansible_lxc 110` so the broken state is replaced by the IaC-defined state, and to leave a note in the troubleshooting runbook if a recurring failure is identified.
