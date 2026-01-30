# node_exporter

Prometheus Node Exporter role.

## Description

This role installs the Prometheus Node Exporter for collecting host-level metrics.

## Tasks

- Installs node_exporter
- Configures collectors
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
    - node_exporter
```

## Ports

- `9100` - Prometheus metrics endpoint

## Files

- Service configuration files

## Handlers

- Service restart handlers

## Metrics Collected

- CPU usage
- Memory usage
- Disk I/O
- Network statistics
- Filesystem usage
- System load

## Notes

Deploy to all containers you want to monitor with Prometheus.
