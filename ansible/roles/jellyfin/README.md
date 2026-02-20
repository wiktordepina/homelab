# jellyfin

Jellyfin media server role.

## Description

This role installs and configures Jellyfin, a free media server for streaming movies, TV shows, and music.

## Tasks

- Installs Jellyfin and dependencies
- Configures media library paths
- Sets up hardware transcoding (with GPU support)

## Requirements

- Debian-based OS
- GPU drivers installed (for hardware transcoding)
- Media storage mounted

## Variables

Refer to `vars/main.yaml` for configuration options.

## Dependencies

- `base`
- `gpu_drivers` (for hardware transcoding)

## Example Usage

```yaml
terraform:
  vmid: 204
  hostname: jellyfin
  unprivileged: false  # Required for GPU access

pve_extra:
  - mp0: /zpool/share/movies,mp=/mnt/movies,backup=0
  - mp1: /zpool/share/shows,mp=/mnt/shows,backup=0
  # GPU passthrough entries
  - lxc.cgroup2.devices.allow: c 195:* rwm
  - lxc.mount.entry: /dev/nvidia0 dev/nvidia0 none bind,optional,create=file

ansible:
  roles:
    - base
    - gpu_drivers
    - jellyfin
```

## Ports

- `8096` - Jellyfin web UI (HTTP)

## Handlers

- Service restart handlers

## Notes

- Container must be privileged (`unprivileged: false`) for GPU access
- Media directories are mounted from the ZFS pool
- NVIDIA GPU enables hardware-accelerated transcoding
