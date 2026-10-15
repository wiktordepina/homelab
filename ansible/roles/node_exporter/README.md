# node_exporter

Prometheus Node Exporter role.

## Description

Installs the Prometheus Node Exporter from the upstream release and runs it as an unprivileged system user. The default collectors work without root: they read `/proc` and `/sys`, and the systemd collector talks to systemd over D-Bus.

## Tasks

- Creates the `node_exporter` system user and group
- Downloads the release tarball and installs the binary to `/etc/node_exporter/`
- Templates and enables the `node_exporter` systemd unit

## Requirements

- Debian-based OS
- On a host behind [egress_proxy](../egress_proxy/README.md), the release download goes direct as root, from `github.com` and `release-assets.githubusercontent.com`.

## Variables

| Variable | Default | Purpose |
|---|---|---|
| `node_exporter_version` | `1.9.1` | Release to install |
| `node_exporter_user` | `node_exporter` | System user and group the service runs as |
| `node_exporter_flags` | `[]` | Extra command-line flags, one per item, e.g. to turn on collectors that are off by default |

A flag is written into `ExecStart` as it is. systemd interprets backslash escapes there, so in a regular expression write `[.]` rather than `\.`.

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - role: node_exporter
      vars:
        node_exporter_flags:
          - --collector.systemd
          - --collector.systemd.unit-include=(claude-.+|maitre-d)[.]service
```

The host must also be added as a scrape job in the [prometheus](../prometheus/README.md) role, and its firewall, if it has one, must open the port to Prometheus.

## Ports

- `9100` - Prometheus metrics endpoint

## Handlers

- `Restart node_exporter service`

## Metrics Collected

The upstream defaults include CPU, memory, disk and network I/O, filesystem usage, load, pressure stall information (PSI, on kernels that expose it) and `/proc/vmstat` counters such as `oom_kill`. Anything else, such as systemd unit states, is enabled through `node_exporter_flags`.

## Notes

The exporter on the PVE host (scraped as `pve_node`) was installed by hand and is not managed by this role.
