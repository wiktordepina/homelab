# homeassistant

Home Assistant role.

## Description

This role installs and configures Home Assistant for home automation.

## Tasks

- Installs Docker (dependency)
- Deploys Home Assistant container
- Configures persistent storage

## Requirements

- Debian-based OS
- Docker

## Variables

Refer to `vars/main.yaml` for configuration options.

## Dependencies

- `base`
- `docker`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - docker
    - homeassistant
```

## Ports

- `8123` - Home Assistant web UI

## Notes

Home Assistant runs as a Docker container with host network mode to enable device discovery and integration with smart home devices.
