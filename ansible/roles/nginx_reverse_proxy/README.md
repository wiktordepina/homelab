# nginx_reverse_proxy

Nginx reverse proxy configuration role.

## Description

This role installs and configures Nginx as a reverse proxy for internal services. It handles SSL termination and routes traffic to backend services.

## Tasks

- Installs Nginx
- Deploys reverse proxy configuration
- Enables and starts Nginx service

## Requirements

- Debian-based OS
- SSL certificates (typically managed by `certbot` role)
- The `catalogue` variable, published by the `service_catalogue` role

## Variables

This role declares no variables of its own. It reads `catalogue.services`, taking each entry's `name` as the hostname prefix and `upstream` as the proxy target, and skipping any entry marked `proxy: false`. See [`docs/reference/service-catalogue.md`](../../../docs/reference/service-catalogue.md).

## Dependencies

- `base`
- `service_catalogue`, which must be listed before this role

## Example Usage

```yaml
ansible:
  roles:
    - base
    - service_catalogue
    - nginx_reverse_proxy
    - certbot
```

## Templates

- `nginx.conf.j2` - Main Nginx configuration with upstream definitions

## Handlers

- `Restart nginx service` - Restarts Nginx on configuration changes

## Notes

The reverse proxy is typically deployed alongside the `certbot` role to manage SSL certificates for the `*.homelab.matagoth.com` wildcard domain.
