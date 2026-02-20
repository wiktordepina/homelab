# LXC Configuration Guide

This guide explains how to define and manage LXC containers using the unified configuration system in this repository.

## Overview

Each LXC container is defined by a single YAML file in `config/lxc/<vmid>.yaml`. This file contains both Terraform provisioning settings and Ansible configuration settings, providing a unified view of each container's infrastructure and application state.

## Configuration Schema

```yaml
---
# Terraform settings for container provisioning
terraform:
  vmid: 201                     # Unique container ID
  hostname: bind9               # Container hostname
  ip_address: 10.20.1.201/16    # IP address with CIDR notation
  nameserver: 10.20.0.1         # DNS server
  cpu_core_count: 4             # Number of CPU cores
  memory: 2048                  # RAM in MB
  swap: 512                     # Swap in MB
  start_on_boot: true           # Auto-start on host boot
  rootfs_size: 20G              # Root filesystem size
  unprivileged: true            # Unprivileged container (default)
  mount_points:                 # Optional mount points
    - key: 1
      storage: '/host/path'
      mp: '/container/path'
      size: 250M

# Extra PVE configuration (applied directly to /etc/pve/lxc/<vmid>.conf)
pve_extra:
  - mp0: /zpool/share/data,mp=/mnt/data,backup=0
  - lxc.cgroup2.devices.allow: c 195:* rwm

# Ansible configuration for the container
ansible:
  roles:
    - base                      # Always include base role
    - role: dns                 # Role with variables
      vars:
        tsig_key: "{{ lookup('ansible.builtin.env', 'DNS_TSIG_KEY') }}"
  tasks:                        # Optional inline tasks
    - name: Custom task
      ansible.builtin.command: echo "Hello"
```

## Terraform Settings

| Property | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `vmid` | integer | ✅ | - | Unique container ID (100-599) |
| `hostname` | string | ✅ | - | Container hostname |
| `ip_address` | string | ✅ | - | IP address with CIDR (e.g., `10.20.1.201/16`) |
| `nameserver` | string | ✅ | - | DNS server IP |
| `cpu_core_count` | integer | ✅ | - | Number of CPU cores |
| `memory` | integer | ✅ | - | RAM in MB |
| `swap` | integer | ❌ | 512 | Swap in MB |
| `start_on_boot` | boolean | ❌ | true | Auto-start container on host boot |
| `rootfs_size` | string | ✅ | - | Root filesystem size (e.g., `20G`, `100G`) |
| `unprivileged` | boolean | ❌ | true | Run as unprivileged container |
| `mount_points` | array | ❌ | [] | Additional mount points |

### Mount Points

Mount points are used for persistent storage that lives outside the container:

```yaml
mount_points:
  - key: 1                    # Mount point index (1-9)
    storage: '/host/path'     # Path on Proxmox host
    mp: '/container/path'     # Mount path inside container
    size: 1G                  # Size allocation
```

## PVE Extra Configuration

The `pve_extra` section allows direct manipulation of the Proxmox LXC configuration file. This is useful for advanced features not exposed through Terraform.

### Common Use Cases

#### GPU Passthrough (NVIDIA)

```yaml
pve_extra:
  - lxc.cgroup2.devices.allow: c 195:* rwm
  - lxc.cgroup2.devices.allow: c 234:* rwm
  - lxc.cgroup2.devices.allow: c 238:* rwm
  - lxc.mount.entry: /dev/nvidia0 dev/nvidia0 none bind,optional,create=file
  - lxc.mount.entry: /dev/nvidiactl dev/nvidiactl none bind,optional,create=file
  - lxc.mount.entry: /dev/nvidia-uvm dev/nvidia-uvm none bind,optional,create=file
  - lxc.mount.entry: /dev/nvidia-uvm-tools dev/nvidia-uvm-tools none bind,optional,create=file
```

#### TUN Device (for VPN/containers)

```yaml
pve_extra:
  - lxc.cgroup2.devices.allow: c 10:200 rwm
  - lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
```

#### Media Library Mounts

```yaml
pve_extra:
  - mp0: /zpool/share/movies,mp=/mnt/movies,backup=0
  - mp1: /zpool/share/shows,mp=/mnt/shows,backup=0
```

## Ansible Configuration

The `ansible` section defines how the container will be configured after provisioning.

### Roles

Roles are reusable configuration modules:

```yaml
ansible:
  roles:
    - base                      # Simple role reference
    - docker
    - role: containers          # Role with variables
      vars:
        containers:
          - name: portainer
            state: up
          - name: homarr
            state: up
```

### Available States for Containers

When using the `containers` role:

| State | Description |
|-------|-------------|
| `up` | Container is running |
| `down` | Container is stopped |
| `destroyed` | Container and config removed |

### Tasks

For simple one-off configurations, use inline tasks:

```yaml
ansible:
  tasks:
    - name: Create directory
      ansible.builtin.file:
        path: /opt/myapp
        state: directory
```

## VMID Allocation

| Range | Purpose |
|-------|---------|
| 100-199 | Infrastructure services (DNS, networking) |
| 200-499 | Application services |
| 500-599 | GitHub Actions runners |

## Creating a New LXC Container

### Step 1: Create Configuration File

Create `config/lxc/<vmid>.yaml`:

```yaml
---
terraform:
  vmid: 212
  hostname: myservice
  ip_address: 10.20.1.212/16
  nameserver: 10.20.0.1
  cpu_core_count: 4
  memory: 4096
  swap: 512
  start_on_boot: true
  rootfs_size: 50G

ansible:
  roles:
    - base
    - docker
```

### Step 2: Provision with Terraform

```bash
./run/execute_runner terraform_lxc 212 apply
```

### Step 3: Configure with Ansible

```bash
./run/execute_runner ansible_lxc 212
```

### Step 4: Add DNS Record (Optional)

Add to `terraform/dns/services.tf`:

```terraform
resource "dns_a_record_set" "myservice" {
  zone      = "home.matagoth.com."
  name      = "myservice"
  addresses = ["10.20.1.212"]
  ttl       = 500
}
```

Then apply:

```bash
./run/execute_runner terraform_dns apply
```

## Examples

### Simple Service Container

```yaml
---
terraform:
  vmid: 202
  hostname: ntfy
  ip_address: 10.20.1.202/16
  nameserver: 10.20.0.1
  cpu_core_count: 4
  memory: 2048
  swap: 512
  start_on_boot: true
  rootfs_size: 20G

ansible:
  roles:
    - base
    - ntfy
```

### Docker Host with Multiple Containers

```yaml
---
terraform:
  vmid: 205
  hostname: dockerhost
  ip_address: 10.20.1.205/16
  nameserver: 10.20.0.1
  cpu_core_count: 12
  memory: 25600
  swap: 2048
  start_on_boot: true
  rootfs_size: 200G

pve_extra:
  - lxc.cgroup2.devices.allow: c 10:200 rwm
  - lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
  - mp0: /zpool/share,mp=/pve/share,backup=0

ansible:
  roles:
    - base
    - docker
    - role: containers
      vars:
        containers:
          - name: portainer
            state: down
          - name: uptime-kuma
            state: down
          - name: homarr
            state: up
          - name: arrs
            state: up
```

### GPU-Enabled Media Server

```yaml
---
terraform:
  vmid: 204
  hostname: jellyfin
  ip_address: 10.20.1.204/16
  nameserver: 10.20.0.1
  cpu_core_count: 6
  memory: 4096
  swap: 1024
  start_on_boot: true
  rootfs_size: 200G
  unprivileged: false

pve_extra:
  - mp0: /zpool/share/movies,mp=/mnt/movies,backup=0
  - mp1: /zpool/share/shows,mp=/mnt/shows,backup=0
  - lxc.cgroup2.devices.allow: c 195:* rwm
  - lxc.cgroup2.devices.allow: c 234:* rwm
  - lxc.mount.entry: /dev/nvidia0 dev/nvidia0 none bind,optional,create=file
  - lxc.mount.entry: /dev/nvidiactl dev/nvidiactl none bind,optional,create=file
  - lxc.mount.entry: /dev/nvidia-uvm dev/nvidia-uvm none bind,optional,create=file

ansible:
  roles:
    - base
    - gpu_drivers
    - jellyfin
```

## Troubleshooting

### Container Won't Start

1. Check Proxmox logs: `journalctl -u pve* -f`
2. Verify IP isn't already in use
3. Check storage availability for rootfs

### Ansible Playbook Fails

1. Ensure container is running and SSH accessible
2. Verify SSH keys are deployed
3. Check required environment variables are set

### GPU Passthrough Not Working

1. Verify NVIDIA drivers installed on Proxmox host
2. Check `pve_extra` cgroup permissions
3. Ensure container is privileged (`unprivileged: false`)
