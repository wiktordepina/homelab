# certbot

Let's Encrypt SSL certificate management role.

## Description

This role installs certbot with Cloudflare DNS plugin for obtaining and renewing SSL certificates using the DNS-01 challenge.

## Tasks

- Installs certbot in virtual environment
- Configures Cloudflare DNS plugin
- Sets up automatic renewal

## Requirements

- Debian-based OS
- Cloudflare API credentials
- Domain managed through Cloudflare DNS

## Variables

Refer to `vars/main.yaml` and templates for configuration.

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - nginx_reverse_proxy
    - certbot
```

## Files

- `cloudflare.ini` - Cloudflare API credentials template

## Manual Certificate Generation

After role deployment, generate certificates:

```bash
/opt/certbot/bin/certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /opt/certbot/cloudflare.ini \
  --dns-cloudflare-propagation-seconds 60 \
  -d matagoth.com \
  -d *.homelab.matagoth.com
```

## Notes

See [CREATE_WILDCARD_SSL_CERT.md](../../../docs/CREATE_WILDCARD_SSL_CERT.md) for detailed certificate generation instructions.
