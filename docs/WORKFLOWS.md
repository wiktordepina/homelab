# Workflows

> **Navigation:** [← Back to README](../README.md) | [Runner Toolbox](RUNNER_TOOLBOX.md) | [LXC Configuration](LXC_CONFIGURATION.md)

This document describes common operational workflows for managing the homelab infrastructure.

## Quick Reference

| Task | Command |
|------|---------|
| Provision LXC | `./run/execute_runner terraform_lxc <vmid> apply` |
| Configure LXC | `./run/execute_runner ansible_lxc <vmid>` |
| Update DNS | `./run/execute_runner terraform_dns apply` |
| Configure PVE | `./run/execute_runner ansible_pve` |

## Adding a New Service

### Complete Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ 1. Create LXC   │────▶│ 2. Terraform    │────▶│ 3. Ansible      │
│    Config       │     │    Provision    │     │    Configure    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ 6. Verify       │◀────│ 5. Update       │◀────│ 4. Add DNS      │
│    Service      │     │    Reverse Proxy│     │    Record       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Step 1: Create LXC Configuration

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
    - role: containers
      vars:
        containers:
          - name: myservice
            state: up
```

### Step 2: Create Docker Compose (if applicable)

Create `config/docker/myservice/docker-compose.yaml`:

```yaml
---
services:
  myservice:
    image: myimage:latest
    container_name: myservice
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - myservice_data:/data

volumes:
  myservice_data:
```

### Step 3: Provision the Container

```bash
./run/execute_runner terraform_lxc 212 plan   # Preview changes
./run/execute_runner terraform_lxc 212 apply  # Apply changes
```

### Step 4: Configure the Container

```bash
./run/execute_runner ansible_lxc 212
```

### Step 5: Add DNS Record (Optional)

Edit `terraform/dns/services.tf`:

```terraform
resource "dns_a_record_set" "myservice" {
  zone      = "home.matagoth.com."
  name      = "myservice"
  addresses = ["10.20.1.212"]
  ttl       = 500
}
```

Apply DNS changes:

```bash
./run/execute_runner terraform_dns apply
```

### Step 6: Update Reverse Proxy (Optional)

Add upstream to nginx configuration and redeploy:

```bash
./run/execute_runner ansible_lxc 110
```

---

## Updating an Existing Service

### Update Container Configuration

1. Edit the LXC config file
2. Re-run Ansible:

```bash
./run/execute_runner ansible_lxc <vmid>
```

### Update Container Resources (CPU/Memory)

1. Edit `config/lxc/<vmid>.yaml`
2. Re-run Terraform:

```bash
./run/execute_runner terraform_lxc <vmid> apply
```

Note: Some changes require container restart.

### Update Docker Stack

1. Edit `config/docker/<stack>/docker-compose.yaml`
2. Re-run Ansible:

```bash
./run/execute_runner ansible_lxc <vmid>
```

The containers role pulls updated images automatically.

---

## Destroying a Service

### Remove Container

```bash
./run/execute_runner terraform_lxc <vmid> destroy
```

### Remove DNS Record

1. Delete the resource from `terraform/dns/services.tf`
2. Apply:

```bash
./run/execute_runner terraform_dns apply
```

### Clean Up Files

- Remove `config/lxc/<vmid>.yaml`
- Remove `config/docker/<stack>/` if applicable

---

## DNS Management

### View Current DNS Records

```bash
./run/execute_runner terraform_dns plan
```

### Add a New DNS Record

Edit `terraform/dns/services.tf`:

```terraform
resource "dns_a_record_set" "newservice" {
  zone      = "home.matagoth.com."
  name      = "newservice"
  addresses = ["10.20.1.xxx"]
  ttl       = 500
}
```

Apply:

```bash
./run/execute_runner terraform_dns apply
```

### DNS File Organization

| File | Purpose |
|------|---------|
| `infra.tf` | Infrastructure DNS (PVE, networking) |
| `services.tf` | Application services |
| `reverse_proxy.tf` | External-facing services |

---

## Proxmox Host Configuration

### Run PVE Playbook

```bash
./run/execute_runner ansible_pve
```

This configures:
- Telegraf metrics agent
- Any host-level settings

### When to Run

- After Proxmox updates
- When changing monitoring configuration
- When adding host-level features

---

## Backup and Recovery

### Proxmox Backup

Backups are managed through Proxmox UI. Key locations:
- ZFS snapshots: `zpool`
- Container configs: `/etc/pve/lxc/`

### Terraform State

Terraform state is stored in `/pve/terraform/` on the host.

### Recovery Steps

1. Restore Proxmox host
2. Mount state directory
3. Re-provision containers: `terraform_lxc <vmid> apply`
4. Re-configure: `ansible_lxc <vmid>`

---

## Troubleshooting Workflows

### Container Won't Provision

```bash
# Check Terraform plan
./run/execute_runner terraform_lxc <vmid> plan

# View Terraform state
./run/execute_runner sh -c "cd terraform/lxc && terraform state list"
```

### Ansible Fails to Connect

1. Verify container is running:
   ```bash
   pct status <vmid>
   ```

2. Test SSH manually:
   ```bash
   ssh root@10.20.1.<vmid>
   ```

3. Check SSH keys are deployed

### Service Not Accessible

1. Verify container IP:
   ```bash
   pct exec <vmid> -- ip addr
   ```

2. Check service is running:
   ```bash
   pct exec <vmid> -- docker ps
   ```

3. Verify DNS resolution:
   ```bash
   dig myservice.home.matagoth.com
   ```

4. Check reverse proxy configuration

---

## CI/CD Pipeline

### Automatic Deployment

The GitHub Actions workflow:

1. Triggers on push to main
2. Runs on self-hosted runner (LXC 5xx)
3. Executes in runner-toolbox container
4. Sends notifications via ntfy

### Manual Trigger

Workflows can be triggered manually from GitHub Actions UI.

### Notification

After workflow completion, ntfy sends status:

```bash
./run/execute_runner ntfy_workflow_status "Deploy LXC 212" "success" "https://github.com/..."
```

---

## Cheat Sheet

```bash
# Provision
terraform_lxc <vmid> plan
terraform_lxc <vmid> apply
terraform_lxc <vmid> destroy

# Configure
ansible_lxc <vmid>
ansible_pve

# DNS
terraform_dns plan
terraform_dns apply

# Debug
render_lxc_playbook <vmid>  # View generated playbook
```
