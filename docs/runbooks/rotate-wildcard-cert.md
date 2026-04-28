# Rotate the wildcard SSL certificate

The LAN-side reverse proxy terminates TLS for the LAN-side proxy zone using a wildcard certificate. The certificate is issued by an ACME provider over a DNS-01 challenge, and renewed automatically by an ACME client running on the proxy container.

This runbook covers what to do when **automatic renewal stops working** — either silently, when the certificate is approaching expiry without having been renewed, or noisily, when a renewal attempt has produced an error. Routine operation needs no manual intervention.

For the design context — which zone this certificate covers, why TLS terminates only at the proxy, the relationship to the public zone — see [concepts/domains-and-tls](../concepts/domains-and-tls.md).

## Pre-conditions

The certificate-renewal mechanism is wired up by the proxy's Ansible roles when the proxy LXC is configured. If the proxy LXC has been provisioned but configuration has not run successfully, this runbook does not apply yet; run configuration first.

The renewal mechanism uses an API credential for the DNS provider hosting the proxy zone. The credential is one of the homelab's secrets and lives in the host's secrets directory, mounted into the runner. If renewal is failing because of a credential problem, the fix is to refresh the credential there, not to change anything inside the proxy container.

## Diagnose first

The most useful first step is to confirm the failure mode. Three states are possible.

**Renewal succeeded recently and the certificate is fresh.** Check the certificate's expiry; if it is months away, the system is healthy and there is nothing to do.

**Renewal is failing repeatedly.** The ACME client logs the failures. Inspect the client's recent logs for the error class — DNS propagation timeout, rate limit, credential rejection, account problem — and address that specific cause.

**Renewal has not been attempted.** The renewal timer is not running, or has been disabled. Check the timer's status on the proxy container; re-enable it if needed.

Each of these has a different remedy; running the renewal manually without diagnosing first wastes a renewal attempt against the rate-limited issuer.

## Common remedies

### DNS propagation timeout

The ACME client provisions a temporary DNS record for the challenge and waits for it to propagate before asking the issuer to verify. Slow propagation occasionally causes timeouts. Re-running with a longer propagation wait usually succeeds. This is a transient failure mode and rarely recurs; if it recurs, the problem is more likely with the DNS provider than with the homelab.

### Credential rejection

If the ACME client cannot create the challenge record, the DNS provider's credential is wrong, expired, or insufficiently scoped. Generate a fresh credential with the right scope (DNS edit, on the relevant zone), update the homelab's secrets, and re-run renewal. Insufficient scope is a recurring trap: the credential needs both *zone read* and *DNS edit* permissions on the zone hosting the proxy domain.

### Rate limit

The issuer enforces both per-domain and per-account rate limits. If a recent batch of failed renewals exhausted the allowance, no further renewal will succeed for some time. The remedy is to wait; in the interim, the existing certificate is still valid. Use the issuer's staging environment when iterating on a fix that requires repeated attempts.

### Disabled or removed timer

If automation has been turned off — sometimes inadvertently, sometimes by a previous troubleshooting session — re-running the proxy container's configuration role re-installs the renewal timer. Manual edits inside the container drift away the next time configuration runs anyway, so this is usually the right fix.

## Triggering a renewal manually

When automation is healthy but a renewal needs to happen *now* — for example, immediately after rotating the DNS-provider credential, to confirm everything works — invoke the ACME client directly on the proxy container with its renewal command. A successful manual run also reloads the proxy so the new certificate is picked up without a process restart; if it does not, reload the proxy by hand afterwards.

Use the issuer's staging environment for any manual run that is not certain to succeed. A manual production run that fails counts against the rate limit.

## After rotation

After a successful renewal:

- Confirm the new certificate's expiry has moved forward by inspecting the certificate from a client that talks to the proxy.
- Confirm the proxy is serving the new certificate; the ACME client's deploy hook should have reloaded the proxy automatically.
- Confirm at least one backend still resolves end-to-end through the proxy by hitting it from a browser.

If automation was the failure mode (timer disabled, hook missing), the next thing to do is to re-run the proxy's configuration role so the broken state is replaced by the IaC-defined state, and to leave a note in the troubleshooting runbook if a recurring failure is identified.
