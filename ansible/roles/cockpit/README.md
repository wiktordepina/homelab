# cockpit

Cockpit web-based server management role.

## Description

This role installs Cockpit, a web-based interface for server administration.

## Tasks

- Installs Cockpit and plugins
- Configures web service
- Enables systemd service

## Requirements

- Debian-based OS

## Variables

Refer to `vars/main.yaml` for configuration.

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - cockpit
```

## Ports

- `9090` - Cockpit web UI

## Handlers

- Service restart handlers

## Notes

Cockpit provides a convenient web interface for file management, system monitoring, and terminal access. Useful for the fileserver container.
