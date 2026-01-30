# telegraf

Telegraf metrics agent role.

## Description

This role installs Telegraf for collecting system metrics and sending them to Prometheus/InfluxDB.

## Tasks

- Installs Telegraf agent
- Configures input and output plugins
- Sets up systemd service

## Requirements

- Debian-based OS

## Variables

None

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - telegraf
```

## Handlers

- Service restart handlers

## Notes

Telegraf is deployed on the Proxmox host to collect hypervisor-level metrics.
