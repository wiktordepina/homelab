# Rotate the wildcard SSL certificate

The LAN-side reverse proxy (LXC 110, `nginx`) terminates TLS for `*.homelab.matagoth.com` using a wildcard certificate. The certificate is issued by Let's Encrypt over a DNS-01 challenge against Cloudflare, and renewed automatically by certbot running on the proxy container.

This runbook covers what to do when **automatic renewal stops working** — either silently, when the certificate is approaching expiry without having been renewed, or noisily, when a renewal attempt has produced an error. It also includes the exact commands for first-time issuance, in case the certificate is ever destroyed and needs to be re-created from scratch. Routine operation needs no manual intervention.

For the design context — which zone this certificate covers, why TLS terminates only at the proxy, the relationship to the public zone — see [concepts/domains-and-tls](../concepts/domains-and-tls.md).

## Pre-conditions

The certificate-renewal mechanism is wired up by the `certbot` and `nginx_reverse_proxy` Ansible roles when LXC 110 is configured. If LXC 110 has been provisioned but configuration has not run successfully, this runbook does not apply yet; run `ansible_lxc 110` first.

The renewal mechanism uses a Cloudflare API token for the DNS-01 challenge against the public zone. The token is one of the homelab's secrets, lives in `/pve/secrets/` on the host, and is mounted into the runner. If renewal is failing because of a credential problem, the fix is to refresh the token there, not to change anything inside the proxy container.

## Diagnose first

The most useful first step is to confirm the failure mode. Three states are possible.

**Renewal succeeded recently and the certificate is fresh.** Check the certificate's expiry; if it is months away, the system is healthy and there is nothing to do.

```bash
# On LXC 110:
openssl x509 -enddate -noout -in /etc/letsencrypt/live/matagoth.com/cert.pem
systemctl list-timers | grep certbot
```

**Renewal is failing repeatedly.** Certbot logs the failures. Inspect the recent certbot logs on LXC 110 for the error class — DNS propagation timeout, rate limit, credential rejection, account problem — and address that specific cause.

```bash
journalctl -u certbot.service -n 200
ls -lt /var/log/letsencrypt/ | head
```

**Renewal has not been attempted.** The renewal systemd timer is not running, or has been disabled. Check the timer's status on LXC 110; re-enable it if needed (or, more reliably, re-run `ansible_lxc 110` to restore it from the role).

```bash
systemctl status certbot.timer
```

Each of these has a different remedy; running the renewal manually without diagnosing first wastes a renewal attempt against the rate-limited issuer.

## Common remedies

### DNS propagation timeout

Certbot provisions a temporary `_acme-challenge` TXT record for the challenge and waits for it to propagate before asking Let's Encrypt to verify. Slow propagation occasionally causes timeouts. Re-running with a longer `--dns-cloudflare-propagation-seconds` value usually succeeds.

```bash
/opt/certbot/bin/certbot renew --dns-cloudflare-propagation-seconds 120
```

This is a transient failure mode and rarely recurs; if it recurs, the problem is more likely with Cloudflare than with the homelab. Useful sanity check that the challenge record is being seen by public DNS:

```bash
dig _acme-challenge.matagoth.com TXT
```

### Credential rejection

If certbot cannot create the challenge record, the Cloudflare token is wrong, expired, or insufficiently scoped. Generate a fresh token in the Cloudflare dashboard (**My Profile → API Tokens → Create Token**, "Edit zone DNS" template) with the right scope:

- **Zone → Zone → Read**
- **Zone → DNS → Edit**

Limit the token to the public zone (`matagoth.com`).

Update the secrets file on the Proxmox host so the runner picks it up next apply. The credentials file inside the container is at `/opt/certbot/cloudflare.ini` and looks like this:

```ini
dns_cloudflare_api_token = your-api-token-here
```

Set restrictive permissions when creating it by hand:

```bash
chmod 600 /opt/certbot/cloudflare.ini
```

Re-run `ansible_lxc 110` to push the credential file into the container, then re-run renewal. Insufficient scope is a recurring trap: a token with only `Zone → Zone → Read` cannot create the challenge record and produces a credential error indistinguishable from a wrong token.

### Rate limit

Let's Encrypt enforces both per-domain and per-account rate limits. If a recent batch of failed renewals exhausted the allowance, no further renewal will succeed for some time. The remedy is to wait; in the interim, the existing certificate is still valid. Use the `--staging` flag when iterating on a fix that requires repeated attempts:

```bash
/opt/certbot/bin/certbot certonly \
  --staging \
  --dns-cloudflare \
  --dns-cloudflare-credentials /opt/certbot/cloudflare.ini \
  -d matagoth.com -d '*.homelab.matagoth.com'
```

### Disabled or removed timer

If automation has been turned off — sometimes inadvertently, sometimes by a previous troubleshooting session — re-running `ansible_lxc 110` re-installs the renewal timer. Manual edits inside the container drift away the next time configuration runs anyway, so this is usually the right fix.

## Triggering a renewal manually

When automation is healthy but a renewal needs to happen *now* — for example, immediately after rotating the Cloudflare token, to confirm everything works — invoke certbot directly on LXC 110:

```bash
# Dry-run first; safe and does not consume rate limit
/opt/certbot/bin/certbot renew --dry-run

# Real renewal
/opt/certbot/bin/certbot renew
```

A successful manual run also reloads nginx so the new certificate is picked up without a process restart. The reload happens through the deploy hook installed by the role, equivalent to:

```bash
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'EOF'
#!/bin/bash
systemctl reload nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

If for any reason the hook did not fire, reload nginx by hand:

```bash
systemctl reload nginx
```

Use the `--staging` flag for any manual run that is not certain to succeed. A manual production run that fails counts against the rate limit.

## First-time issuance

Used only when the certificate was destroyed entirely or this is a fresh proxy container. The role normally takes care of this; the explicit command is here for emergency use:

```bash
/opt/certbot/bin/certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /opt/certbot/cloudflare.ini \
  --dns-cloudflare-propagation-seconds 60 \
  -d matagoth.com \
  -d '*.homelab.matagoth.com'
```

After issuance, the certificate files live at:

| File              | Path                                                    |
|-------------------|---------------------------------------------------------|
| Certificate chain | `/etc/letsencrypt/live/matagoth.com/fullchain.pem`      |
| Private key       | `/etc/letsencrypt/live/matagoth.com/privkey.pem`        |
| Certificate only  | `/etc/letsencrypt/live/matagoth.com/cert.pem`           |
| CA chain          | `/etc/letsencrypt/live/matagoth.com/chain.pem`          |

Nginx references them in its server block:

```nginx
server {
    listen 443 ssl;
    server_name *.homelab.matagoth.com;

    ssl_certificate     /etc/letsencrypt/live/matagoth.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/matagoth.com/privkey.pem;

    # ... rest of configuration
}
```

## After rotation

After a successful renewal:

- Confirm the new certificate's expiry has moved forward by inspecting the certificate from a client that talks to the proxy.
- Confirm nginx is serving the new certificate; certbot's deploy hook should have reloaded nginx automatically.
- Confirm at least one backend still resolves end-to-end through the proxy by hitting it from a browser.

If automation was the failure mode (timer disabled, hook missing), the next thing to do is to re-run `ansible_lxc 110` so the broken state is replaced by the IaC-defined state, and to leave a note in the troubleshooting runbook if a recurring failure is identified.
