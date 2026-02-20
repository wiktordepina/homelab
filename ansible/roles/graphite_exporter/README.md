# graphite_exporter

Graphite metrics exporter role.

## Description

This role installs the Graphite exporter, which receives Graphite-protocol metrics and exposes them in Prometheus format.

## Tasks

- Installs graphite_exporter
- Configures metric mappings
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
    - base
    - prometheus
    - graphite_exporter
```

## Ports

- `9108` - Prometheus metrics endpoint
- `9109` - Graphite receiver

## Files

- Configuration and mapping files

## Handlers

- Service restart handlers

## Notes

Used to bridge legacy Graphite-format metrics into the Prometheus ecosystem.
