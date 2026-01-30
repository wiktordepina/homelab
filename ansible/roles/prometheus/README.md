# prometheus

Prometheus monitoring server role.

## Description

This role installs and configures Prometheus for collecting and storing metrics from homelab services.

## Tasks

- Creates prometheus user and group
- Downloads and installs Prometheus binaries
- Deploys configuration
- Sets up systemd service

## Requirements

- Debian-based OS
- Persistent storage mount (recommended)

## Variables

None (configuration is in files)

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - prometheus
    - graphite_exporter
    - graphana
```

## Files

- `prometheus.yaml` - Prometheus scrape configuration
- `prometheus.service` - Systemd service unit

## Handlers

- `Restart prometheus service` - Restarts Prometheus on config changes

## Ports

- `9090` - Prometheus web UI and API

## Data Directory

Prometheus data is stored in `/prometheus_data/`. It's recommended to mount persistent storage at this location:

```yaml
pve_extra:
  - mp0: /zpool/prometheus,mp=/prometheus_data,backup=0
```

## Notes

The Prometheus instance is typically used with Grafana for visualization and the node_exporter for host metrics.
