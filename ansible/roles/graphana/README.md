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

## Provisioning

The Prometheus datasource and every dashboard come from this role, not from the UI. Grafana reads them from its default provisioning path, `/etc/graphana/conf/provisioning/`:

| Source in the role | Installed to | Picked up |
|---|---|---|
| `files/provisioning/datasources/` | `/etc/graphana/conf/provisioning/datasources/` | at start-up (the copy restarts Grafana) |
| `files/provisioning/dashboards/` | `/etc/graphana/conf/provisioning/dashboards/` | at start-up |
| `files/dashboards/*.json` | `/etc/graphana/dashboards/` | within seconds, no restart |

The datasource keeps the UID `bewhi3wyusoaoc`, which Grafana generated when it was first created by hand. Dashboards refer to it by that UID, so changing it would break every one of them.

Provisioned dashboards cannot be saved from the UI (`allowUiUpdates: false`). The file in the repository is the only source of truth, and a UI save would otherwise be overwritten on the next poll without warning.

### Adding or changing a dashboard

1. Build or edit it in the UI. A provisioned dashboard can't be saved, so use **Save as** to make a scratch copy and work on that.
2. Export it: **Share → Export → Export as JSON**, with **Export for sharing externally** left off, so datasource references keep the UID instead of turning into `${DS_...}` inputs.
3. Save it as `files/dashboards/<slug>.json`. If it replaces an existing one, keep that dashboard's `uid` so links to it keep working, and delete the scratch copy from the UI.
4. Converge the Prometheus container (210).

### Removing a dashboard

Deleting the JSON from the repository does not delete it from the host. Remove `/etc/graphana/dashboards/<slug>.json` on 210 as well, and Grafana drops the dashboard on its next poll.

## Notes

Grafana is typically deployed alongside Prometheus on the monitoring container.

Some dashboards still exist only in Grafana's database, created by hand before provisioning was added. They keep working, but they are not in IaC. Bring each one into `files/dashboards/` using the steps above.
