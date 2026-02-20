# Create Wildcard SSL Certificates with Certbot

> **Navigation:** [← Back to README](../README.md) | [Nginx Role](../ansible/roles/nginx_reverse_proxy/README.md) | [Certbot Role](../ansible/roles/certbot/README.md)

## Overview

This guide explains how to generate wildcard SSL certificates using certbot with the Cloudflare DNS-01 challenge. This allows HTTPS for all `*.homelab.matagoth.com` subdomains without needing individual certificates.

## Prerequisites

- LXC 110 (nginx) provisioned and configured
- Certbot role deployed (`ansible_lxc 110`)
- Cloudflare API credentials in `/opt/certbot/cloudflare.ini`
- Domain managed through Cloudflare DNS

## Generate Certificate

Run the following on the nginx reverse proxy node (LXC 110):

```bash
/opt/certbot/bin/certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /opt/certbot/cloudflare.ini \
  --dns-cloudflare-propagation-seconds 60 \
  -d matagoth.com \
  -d *.homelab.matagoth.com
```

## Certificate Location

Certificates are stored in:

| File | Path |
|------|------|
| Certificate Chain | `/etc/letsencrypt/live/matagoth.com/fullchain.pem` |
| Private Key | `/etc/letsencrypt/live/matagoth.com/privkey.pem` |
| Certificate Only | `/etc/letsencrypt/live/matagoth.com/cert.pem` |
| CA Chain | `/etc/letsencrypt/live/matagoth.com/chain.pem` |

## Nginx Configuration

Reference the certificates in your nginx configuration:

```nginx
server {
    listen 443 ssl;
    server_name *.homelab.matagoth.com;
    
    ssl_certificate /etc/letsencrypt/live/matagoth.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/matagoth.com/privkey.pem;
    
    # ... rest of configuration
}
```

## Auto-Renewal

Certbot sets up automatic renewal via systemd timer. Verify with:

```bash
systemctl status certbot.timer
systemctl list-timers | grep certbot
```

To manually test renewal:

```bash
/opt/certbot/bin/certbot renew --dry-run
```

## Cloudflare API Credentials

Create the credentials file (`/opt/certbot/cloudflare.ini`):

```ini
dns_cloudflare_api_token = your-api-token-here
```

Set restrictive permissions:

```bash
chmod 600 /opt/certbot/cloudflare.ini
```

### Creating Cloudflare API Token

1. Go to Cloudflare Dashboard → My Profile → API Tokens
2. Click "Create Token"
3. Use "Edit zone DNS" template
4. Configure permissions:
   - Zone → DNS → Edit
   - Zone → Zone → Read
5. Limit to specific zone (your domain)

## Restart Nginx After Renewal

Create a deploy hook to automatically reload nginx:

```bash
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh << 'EOF'
#!/bin/bash
systemctl reload nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

## Troubleshooting

### DNS Propagation Timeout

If certificate generation fails due to DNS propagation, increase the wait time:

```bash
--dns-cloudflare-propagation-seconds 120
```

### Verify DNS Record Creation

Check if certbot can create DNS records:

```bash
dig _acme-challenge.matagoth.com TXT
```

### Rate Limits

Let's Encrypt has rate limits. For testing, use the staging environment:

```bash
/opt/certbot/bin/certbot certonly \
  --staging \
  --dns-cloudflare \
  # ... rest of options
```

## Related Documentation

- [Nginx Reverse Proxy Role](../ansible/roles/nginx_reverse_proxy/README.md)
- [Certbot Role](../ansible/roles/certbot/README.md)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
