# nvidia_container_toolkit

NVIDIA Container Toolkit role.

## Description

Installs and configures `nvidia-container-toolkit`, which lets the Docker runtime expose the host's NVIDIA driver to containers (NVENC/NVDEC, CUDA, etc).

## Where to apply

This role runs **inside the LXC that hosts the Docker workload needing GPU access**. It is not for the PVE host (Proxmox does not run user Docker workloads) and is not needed by services that use the GPU directly via the Linux device files (e.g. Jellyfin, which is installed natively as `jellyfin-server`).

## Tasks

- Adds the NVIDIA Container Toolkit apt repo (with signed-by keyring)
- Installs `nvidia-container-toolkit`
- Runs `nvidia-ctk runtime configure --runtime=docker` to wire the runtime into Docker's config
- Restarts Docker to pick up the runtime change

## Requirements

- LXC must be privileged (`unprivileged: false`) and have `/dev/nvidia*` device files bind-mounted from the host (declared in the container's `pve_extra` section).
- `gpu_drivers` role must run before this one — the toolkit depends on the userspace NVIDIA driver libs being present.
- `docker` role must be installed before this one.

## Variables

None.

## Dependencies

- `base`
- `docker`
- `gpu_drivers` (userspace mode)

## Example usage

```yaml
ansible:
  roles:
    - base
    - docker
    - gpu_drivers
    - nvidia_container_toolkit
```

## Notes

- The role uses the `signed-by` apt source format (Ansible's `apt_key` module is deprecated). The keyring is downloaded fresh on each run; apt's source list pins to that file.
