# nvidia_container_toolkit

NVIDIA Container Toolkit role.

## Description

This role installs the NVIDIA Container Toolkit to enable GPU access within Docker containers.

## Tasks

- Installs nvidia-container-toolkit
- Configures Docker runtime
- Restarts Docker to apply changes

## Requirements

- Docker installed
- NVIDIA GPU drivers installed
- Privileged container

## Variables

None

## Dependencies

- `base`
- `docker`
- `gpu_drivers`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - docker
    - gpu_drivers
    - nvidia_container_toolkit
```

## Files

- Configuration files for container runtime

## Notes

Required for running GPU-accelerated Docker containers (e.g., LocalAI with CUDA support).
