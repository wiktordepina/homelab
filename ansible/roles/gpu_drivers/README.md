# gpu_drivers

NVIDIA GPU driver installation role.

## Description

This role installs NVIDIA GPU drivers for hardware acceleration in LXC containers.

## Tasks

- Installs NVIDIA driver packages
- Configures driver for container use

## Requirements

- Debian-based OS
- NVIDIA GPU passed through to container
- Privileged container mode

## Variables

Refer to `vars/main.yaml` for driver version configuration.

## Dependencies

- `base`

## Example Usage

```yaml
terraform:
  unprivileged: false  # Required

pve_extra:
  - lxc.cgroup2.devices.allow: c 195:* rwm
  - lxc.cgroup2.devices.allow: c 234:* rwm
  - lxc.mount.entry: /dev/nvidia0 dev/nvidia0 none bind,optional,create=file
  - lxc.mount.entry: /dev/nvidiactl dev/nvidiactl none bind,optional,create=file
  - lxc.mount.entry: /dev/nvidia-uvm dev/nvidia-uvm none bind,optional,create=file

ansible:
  roles:
    - base
    - gpu_drivers
```

## Notes

- Proxmox host must have NVIDIA drivers installed
- Container must be privileged for GPU device access
- Used by services requiring hardware transcoding (Jellyfin) or AI workloads (LocalAI)
