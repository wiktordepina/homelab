# cloudflared

Cloudflare Tunnel client role.

## Description

This role installs and configures cloudflared, the Cloudflare Tunnel client, to securely expose internal services to the internet without opening firewall ports.

## Tasks

- Installs cloudflared
- Configures tunnel authentication
- Sets up systemd service

## Requirements

- Debian-based OS
- Cloudflare account with tunnel configured
- Tunnel token from Cloudflare dashboard

## Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `cloudflared_tunnel_token` | ✅ | - | Cloudflare tunnel authentication token |

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - role: cloudflared
      vars:
        cloudflared_tunnel_token: "{{ lookup('ansible.builtin.env', 'CLOUDFLARE_TUNNEL_TOKEN') }}"
```

## Notes

The tunnel token is obtained from the Cloudflare Zero Trust dashboard when creating a new tunnel. This allows secure, outbound-only connections to Cloudflare's edge network.
