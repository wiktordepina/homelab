# Docker Stacks

This document describes the Docker Compose stacks available in `config/docker/`.

## Overview

Docker stacks are deployed to LXC containers using the `containers` Ansible role. Each stack is defined in its own directory with a `docker-compose.yaml` file.

## Stack Deployment

Stacks are deployed by specifying them in the LXC configuration:

```yaml
ansible:
  roles:
    - base
    - docker
    - role: containers
      vars:
        containers:
          - name: portainer    # Must match directory name
            state: up          # up, down, or destroyed
```

## Available Stacks

### portainer

**Purpose:** Docker management UI

| Port | Service |
|------|---------|
| 9443 | Portainer Web UI (HTTPS) |

**Host:** dockerhost (LXC 205)

```yaml
- name: portainer
  state: up
```

---

### uptime-kuma

**Purpose:** Self-hosted monitoring and status page

| Port | Service |
|------|---------|
| 3001 | Uptime Kuma Web UI |

**Host:** dockerhost (LXC 205)

```yaml
- name: uptime-kuma
  state: up
```

---

### homarr

**Purpose:** Dashboard and application organizer

| Port | Service |
|------|---------|
| 7575 | Homarr Web UI |

**Host:** dockerhost (LXC 205)

**Required Environment Variables:**
- `HOMARR_SECRET_ENCRYPTION_KEY` - Encryption key for secrets

```yaml
- name: homarr
  state: up
```

---

### arrs

**Purpose:** Media automation stack (Sonarr, Radarr, Prowlarr, qBittorrent) with VPN

| Port | Service |
|------|---------|
| 9696 | Prowlarr (Indexer manager) |
| 8989 | Sonarr (TV shows) |
| 7878 | Radarr (Movies) |
| 8888 | qBittorrent (Torrent client) |
| 8191 | FlareSolverr (Captcha solver) |

**Host:** dockerhost (LXC 205)

**Required Environment Variables:**
- `VPN_ENDPOINT_IP_IRELAND`
- `VPN_ENDPOINT_PORT_IRELAND`
- `WIREGUARD_PUBLIC_KEY_IRELAND`
- `WIREGUARD_PRIVATE_KEY_IRELAND`
- `WIREGUARD_ADDRESSES_IRELAND`

**Components:**
- **Gluetun** - VPN container (WireGuard)
- **Prowlarr** - Indexer manager
- **Sonarr** - TV show management
- **Radarr** - Movie management
- **qBittorrent** - Torrent client
- **FlareSolverr** - Cloudflare bypass

**Notes:**
- All traffic routes through Gluetun VPN container
- Requires TUN device access (configured in `pve_extra`)

```yaml
pve_extra:
  - lxc.cgroup2.devices.allow: c 10:200 rwm
  - lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
```

---

### n8n

**Purpose:** Workflow automation platform

| Port | Service |
|------|---------|
| 5678 | n8n Web UI |

**Host:** n8n (LXC 211)

**Environment Configuration:**
- `N8N_HOST` - Hostname for webhooks
- `WEBHOOK_URL` - External webhook URL

```yaml
- name: n8n
  state: up
```

---

### openwebui

**Purpose:** ChatGPT-like interface for local LLMs

| Port | Service |
|------|---------|
| 80 | Open WebUI |
| 9099 | Pipelines API |

**Host:** localai (LXC 207)

**Components:**
- **Open WebUI** - Chat interface
- **Pipelines** - Custom pipeline extensions

```yaml
- name: openwebui
  state: up
```

---

### litellm

**Purpose:** LLM API proxy supporting multiple providers

| Port | Service |
|------|---------|
| 4000 | LiteLLM API |
| 5432 | PostgreSQL (internal) |

**Host:** localai (LXC 207)

**Required Environment Variables:**
- `LITELLM_DB_PWD` - Database password
- `LITELLM_MASTER_KEY` - API master key
- `LITELLM_SALT_KEY` - Salt for encryption
- `UI_PASSWORD` - Web UI password

**Components:**
- **LiteLLM** - API proxy
- **PostgreSQL** - Configuration database

```yaml
- name: litellm
  state: up
```

---

### actualbudget

**Purpose:** Personal budgeting application

| Port | Service |
|------|---------|
| 5006 | Actual Budget Web UI |

**Host:** dockerhost (LXC 205)

```yaml
- name: actualbudget
  state: up
```

---

### wallos

**Purpose:** Subscription tracking and management

| Port | Service |
|------|---------|
| 8282 | Wallos Web UI |

**Host:** dockerhost (LXC 205)

```yaml
- name: wallos
  state: up
```

---

## Adding a New Stack

### 1. Create Stack Directory

```bash
mkdir -p config/docker/myservice
```

### 2. Create docker-compose.yaml

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

### 3. Add to LXC Configuration

Edit the target LXC's configuration:

```yaml
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

### 4. Deploy

```bash
./run/execute_runner ansible_lxc <vmid>
```

## Using Environment Variables

Docker Compose files support Ansible templating for secrets:

```yaml
environment:
  - API_KEY={{ lookup('ansible.builtin.env', 'MY_API_KEY') }}
```

Secrets are sourced from `/pve/secrets/` on the runner.

## Stack Locations

| Stack | LXC Host | IP Address |
|-------|----------|------------|
| portainer | dockerhost (205) | 10.20.1.205 |
| uptime-kuma | dockerhost (205) | 10.20.1.205 |
| homarr | dockerhost (205) | 10.20.1.205 |
| arrs | dockerhost (205) | 10.20.1.205 |
| actualbudget | dockerhost (205) | 10.20.1.205 |
| wallos | dockerhost (205) | 10.20.1.205 |
| n8n | n8n (211) | 10.20.1.211 |
| openwebui | localai (207) | 10.20.1.207 |
| litellm | localai (207) | 10.20.1.207 |
