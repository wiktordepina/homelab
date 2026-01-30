# graphana

Grafana dashboard role.

## Description

This role installs and configures Grafana for metrics visualization and dashboards.

## Tasks

- Installs Grafana
- Configures data sources
- Sets up systemd service

## Requirements

- Debian-based OS
- Prometheus (or other data source) available

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
    - graphana
```

## Ports

- `3000` - Grafana web UI

## Files

- Configuration files in `files/`

## Handlers

- Service restart handlers

## Notes

Grafana is typically deployed alongside Prometheus on the monitoring container.
