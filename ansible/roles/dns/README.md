# dns

BIND9 DNS server configuration role.

## Description

This role installs and configures BIND9 as an authoritative DNS server for the internal network zone `home.matagoth.com`.

## Tasks

- Installs BIND9 and utilities
- Configures logging
- Sets up DNS zones
- Configures TSIG key for secure DNS updates (used by Terraform)

## Requirements

- Debian-based OS
- Network connectivity

## Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `tsig_key` | ✅ | - | TSIG key for DNS update authentication |
| `dns_ip` | ✅ | - | IP address of the DNS server |

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - role: dns
      vars:
        tsig_key: "{{ lookup('ansible.builtin.env', 'DNS_TSIG_KEY') }}"
        dns_ip: 10.20.1.201
```

## Files

- `named.conf.options` - BIND9 global options
- `named.conf.local` - Local zone definitions

## Templates

- `tsig-key.key.j2` - TSIG key configuration
- `home-matagoth-com.zone.j2` - Zone file template

## Notes

The DNS server is configured to accept dynamic updates via TSIG authentication, enabling Terraform to manage DNS records programmatically.
