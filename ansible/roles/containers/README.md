# containers

Docker container deployment role.

## Description

This role manages Docker Compose stacks from the `config/docker/` directory. It copies compose files to the target host and manages container lifecycle.

## Tasks

- Copies Docker Compose files to `/containers/<name>/`
- Manages container state (up, down, destroyed)
- Prunes unused Docker images
- Updates container images

## Requirements

- Docker installed on target host
- Docker Compose files in `config/docker/<name>/docker-compose.yaml`

## Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `containers` | ✅ | - | List of containers to manage |

### Container Definition

```yaml
containers:
  - name: portainer      # Must match folder name in config/docker/
    state: up            # up, down, or destroyed
```

### Container States

| State | Description |
|-------|-------------|
| `up` | Container is started/running |
| `down` | Container is stopped |
| `destroyed` | Container and configuration removed |

## Dependencies

- `base`
- `docker`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - docker
    - role: containers
      vars:
        containers:
          - name: portainer
            state: up
          - name: homarr
            state: up
          - name: uptime-kuma
            state: down
```

## Directory Structure

```
/containers/
├── portainer/
│   └── docker-compose.yaml
├── homarr/
│   └── docker-compose.yaml
└── uptime-kuma/
    └── docker-compose.yaml
```

## Notes

- Container compose files must exist in `config/docker/<name>/` before running this role
- The role automatically pulls updated images on each run
- Unused images are pruned to save disk space
