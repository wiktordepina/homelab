# docker

Docker engine installation role.

## Description

This role installs Docker CE (Community Edition) and related tools on Debian-based systems.

## Tasks

- Adds Docker's official GPG key
- Configures Docker apt repository
- Installs Docker CE, CLI, containerd, and plugins
- Enables TUN module for VPN/networking support

## Requirements

- Debian-based OS
- Network connectivity to Docker repositories

## Variables

None

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - docker
```

## Installed Packages

- `docker-ce` - Docker daemon
- `docker-ce-cli` - Docker CLI
- `containerd.io` - Container runtime
- `docker-buildx-plugin` - BuildKit builder
- `docker-compose-plugin` - Docker Compose v2

## Handlers

- `Reboot` - Reboots the system (triggered when TUN module is added)

## Notes

After installation, Docker is ready for use. The TUN module is loaded to support containers that need VPN or advanced networking capabilities.
