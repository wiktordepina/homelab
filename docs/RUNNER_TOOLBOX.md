# Runner Toolbox

The runner toolbox is a Docker-based CI/CD environment that provides all necessary tools for infrastructure provisioning and configuration management.

## Overview

The toolbox is used by GitHub Actions runners to execute Terraform and Ansible operations in a consistent, reproducible environment.

```
┌─────────────────────────────────────────────────────────┐
│                  GitHub Actions Runner                  │
│                     (LXC 500-599)                       │
├─────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────┐  │
│  │              Runner Toolbox Container             │  │
│  │                                                   │  │
│  │  • Terraform + tfenv                              │  │
│  │  • Ansible + community.docker collection         │  │
│  │  • Python (uv managed)                           │  │
│  │  • jq, yq, curl, git                             │  │
│  │                                                   │  │
│  │  Mounts:                                          │  │
│  │  • /pve/secrets   → Credentials                   │  │
│  │  • /pve/terraform → Terraform state               │  │
│  │  • /root/.ssh     → SSH keys                      │  │
│  │  • /build         → Repository                    │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Building the Toolbox

```bash
cd runner-toolbox
docker build -t runner-toolbox .
```

### Build Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `BASE_IMAGE_TAG` | 12 | Debian version |
| `TERRAFORM_VERSION` | 1.12.2 | Terraform version to install |
| `HCLEDIT_VERSION` | 0.2.17 | HCL editor version |
| `UV_VERSION` | 0.8.4 | UV package manager version |

## Running the Toolbox

Use the helper script:

```bash
./run/execute_runner <script> [args...]
```

Or run directly:

```bash
docker run --rm \
  --name runner \
  -v /pve/terraform:/pve/terraform \
  -v /pve/secrets:/pve/secrets \
  -v /home/runner/.ssh:/root/.ssh \
  -v .:/build \
  -w /build \
  runner-toolbox \
  <command>
```

## Available Scripts

Scripts are located in `runner-toolbox/scripts/`:

### terraform_lxc

Provisions or destroys an LXC container using Terraform.

```bash
./run/execute_runner terraform_lxc <vmid> <action>
```

| Argument | Description |
|----------|-------------|
| `vmid` | LXC container ID (e.g., 204) |
| `action` | `plan`, `apply`, or `destroy` |

**Example:**
```bash
./run/execute_runner terraform_lxc 212 apply
```

### ansible_lxc

Configures an LXC container using Ansible.

```bash
./run/execute_runner ansible_lxc <vmid>
```

| Argument | Description |
|----------|-------------|
| `vmid` | LXC container ID |

**Example:**
```bash
./run/execute_runner ansible_lxc 204
```

### ansible_pve

Runs the Proxmox host playbook.

```bash
./run/execute_runner ansible_pve
```

### terraform_dns

Manages DNS records via Terraform.

```bash
./run/execute_runner terraform_dns <action>
```

| Argument | Description |
|----------|-------------|
| `action` | `plan`, `apply`, or `destroy` |

### render_lxc_playbook

Generates an Ansible playbook from LXC configuration.

```bash
./run/execute_runner render_lxc_playbook <vmid>
```

This script is typically called internally by `ansible_lxc`.

### ntfy_workflow_status

Sends workflow status notifications to ntfy.

```bash
./run/execute_runner ntfy_workflow_status <name> <status> <url>
```

## Helper Functions

Functions are located in `runner-toolbox/functions/`:

### ansible.sh

| Function | Description |
|----------|-------------|
| `run_ansible_lxc <vmid>` | Generate and run Ansible playbook for LXC |
| `run_ansible_pve` | Run Proxmox host playbook |

### terraform.sh

| Function | Description |
|----------|-------------|
| `inject_tf_var_for_lxc <vmid> <folder> <var>` | Inject single Terraform variable |
| `inject_tf_lxc_config <vmid> <folder>` | Inject all variables from LXC config |
| `run_terraform_lxc <vmid> <action>` | Run Terraform for LXC container |
| `run_terraform_dns <action>` | Run Terraform for DNS records |

### misc.sh

| Function | Description |
|----------|-------------|
| `check_null <name> <value>` | Validate required parameters |
| `lxc_config <vmid> <query>` | Query LXC configuration YAML |

### ntfy.sh

| Function | Description |
|----------|-------------|
| `ntfy_msg <topic> <title> <msg> [tags] [header]` | Send ntfy notification |
| `run_ntfy_workflow_status <name> <status> <url>` | Send workflow notification |

## Environment Variables

The toolbox expects secrets to be available in `/pve/secrets/`. Scripts in this directory are sourced automatically:

```bash
# /pve/secrets/proxmox.sh
export PM_API_URL="https://192.168.200.100:8006/api2/json"
export PM_API_TOKEN_ID="root@pam!terraform"
export PM_API_TOKEN_SECRET="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
export PM_PASS="your-password"

# /pve/secrets/dns.sh
export DNS_TSIG_KEY="your-tsig-key"

# /pve/secrets/cloudflare.sh
export CLOUDFLARE_TUNNEL_TOKEN="your-token"

# /pve/secrets/ntfy.sh
export NTFY_CREDS="user:password"
```

## Directory Structure

```
runner-toolbox/
├── Dockerfile              # Container image definition
├── pyproject.toml          # Python dependencies (Ansible, ruamel.yaml)
├── functions/              # Bash helper functions
│   ├── ansible.sh
│   ├── misc.sh
│   ├── ntfy.sh
│   └── terraform.sh
├── provider/               # Custom Terraform providers
│   └── terraform-provider-proxmox
└── scripts/                # Executable entry points
    ├── ansible_lxc
    ├── ansible_pve
    ├── ntfy_workflow_status
    ├── render_lxc_playbook
    ├── terraform_dns
    └── terraform_lxc
```

## Workflow Example

Complete workflow to add a new service:

```bash
# 1. Create LXC configuration
cat > config/lxc/212.yaml << 'EOF'
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
EOF

# 2. Provision the container
./run/execute_runner terraform_lxc 212 apply

# 3. Configure the container
./run/execute_runner ansible_lxc 212

# 4. Add DNS record (optional)
# Edit terraform/dns/services.tf, then:
./run/execute_runner terraform_dns apply
```

## Troubleshooting

### Container Can't Access Secrets

Ensure mount points are correct:
```bash
ls -la /pve/secrets/
ls -la /pve/terraform/
```

### Terraform State Lock

If Terraform complains about state lock:
```bash
# Check for stale locks
ls -la /pve/terraform/lxc/
# Remove if necessary (carefully!)
rm /pve/terraform/lxc/.terraform.lock.hcl
```

### SSH Connection Refused

1. Verify container is running: `pct status <vmid>`
2. Check SSH keys are deployed
3. Verify network connectivity
