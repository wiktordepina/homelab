# Network Architecture

> **Navigation:** [← Back to README](../README.md)

This document describes the network architecture and IP addressing scheme for the homelab.

## Network Overview

```
                                    ┌─────────────────────────────────┐
                                    │         Internet                │
                                    └─────────────┬───────────────────┘
                                                  │
                                    ┌─────────────▼───────────────────┐
                                    │     Cloudflare Tunnel           │
                                    │     (cloudflared LXC 208)       │
                                    └─────────────┬───────────────────┘
                                                  │
┌─────────────────────────────────────────────────┼─────────────────────────────────────────────────┐
│                                    Homelab Network (10.20.0.0/16)                                 │
│                                                 │                                                 │
│   ┌─────────────────────────────────────────────┼─────────────────────────────────────────────┐   │
│   │                                             │                                             │   │
│   │   ┌───────────────┐     ┌───────────────────▼───────────────────┐     ┌───────────────┐   │   │
│   │   │   Pi-hole     │     │          nginx reverse proxy          │     │    bind9      │   │   │
│   │   │  10.20.1.1    │◀────│             10.20.1.10                │────▶│  10.20.1.201  │   │   │
│   │   │   DNS sink    │     │         SSL termination               │     │  Internal DNS │   │   │
│   │   └───────────────┘     └───────────────────────────────────────┘     └───────────────┘   │   │
│   │                                             │                                             │   │
│   │                          ┌──────────────────┼──────────────────┐                          │   │
│   │                          │                  │                  │                          │   │
│   │                          ▼                  ▼                  ▼                          │   │
│   │               ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐              │   │
│   │               │    Services      │ │    Services      │ │    Services      │              │   │
│   │               │  10.20.1.202-211 │ │  (Docker hosts)  │ │   (Monitoring)   │              │   │
│   │               └──────────────────┘ └──────────────────┘ └──────────────────┘              │   │
│   │                                                                                           │   │
│   └───────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                   │
│   ┌───────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              Proxmox VE Host                                              │   │
│   │                            192.168.200.100                                                │   │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                      │   │
│   │   │   ZFS Pool  │  │   Telegraf  │  │  NVIDIA GPU │  │   Storage   │                      │   │
│   │   │   ~50TB     │  │   Metrics   │  │  Passthrough│  │   Mounts    │                      │   │
│   │   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘                      │   │
│   └───────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## IP Address Allocation

### Network Ranges

| Range | CIDR | Purpose |
|-------|------|---------|
| 10.20.0.0/16 | 10.20.0.0 - 10.20.255.255 | Homelab internal network |
| 192.168.200.0/24 | 192.168.200.0 - 192.168.200.255 | Management network |

### Static Allocations

#### Infrastructure (10.20.0.x - 10.20.1.99)

| IP Address | Hostname | Purpose |
|------------|----------|---------|
| 10.20.0.1 | gateway | Network gateway |
| 10.20.1.1 | pihole | DNS sinkhole (primary DNS) |
| 10.20.1.10 | nginx | Reverse proxy, SSL termination |

#### Services (10.20.1.200 - 10.20.1.254)

| IP Address | LXC ID | Hostname | Purpose |
|------------|--------|----------|---------|
| 10.20.1.201 | 201 | bind9 | Authoritative DNS |
| 10.20.1.202 | 202 | ntfy | Push notifications |
| 10.20.1.203 | 203 | fileserver | File server (Cockpit) |
| 10.20.1.204 | 204 | jellyfin | Media server |
| 10.20.1.205 | 205 | dockerhost | Multi-container host |
| 10.20.1.206 | 206 | homeassistant | Home automation |
| 10.20.1.207 | 207 | localai | Local LLM services |
| 10.20.1.208 | 208 | cloudflared | Cloudflare tunnel |
| 10.20.1.209 | 209 | signumminer | Signum miner |
| 10.20.1.210 | 210 | prometheus | Monitoring |
| 10.20.1.211 | 211 | n8n | Workflow automation |

#### Management (192.168.200.x)

| IP Address | Hostname | Purpose |
|------------|----------|---------|
| 192.168.200.100 | pve | Proxmox VE host |

## VMID Allocation Scheme

| Range | Purpose | Example |
|-------|---------|---------|
| 100-199 | Infrastructure LXC | 100 (pihole), 110 (nginx) |
| 200-499 | Application LXC | 201-211 (services) |
| 500-599 | GitHub Actions runners | 500, 501, etc. |

## DNS Architecture

```
                    ┌─────────────────┐
                    │  Client Request │
                    │  jellyfin.home. │
                    │   matagoth.com  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │    Pi-hole      │
                    │   10.20.1.1     │
                    │  (DNS sinkhole) │
                    └────────┬────────┘
                             │ Forwards to
                    ┌────────▼────────┐
                    │     bind9       │
                    │  10.20.1.201    │
                    │ (Authoritative) │
                    └────────┬────────┘
                             │ Returns
                    ┌────────▼────────┐
                    │   10.20.1.204   │
                    │  (jellyfin IP)  │
                    └─────────────────┘
```

### DNS Zones

| Zone | Type | Purpose |
|------|------|---------|
| home.matagoth.com | Internal | Internal service resolution |
| homelab.matagoth.com | External | External access via Cloudflare |

### DNS Record Management

Internal DNS records are managed via Terraform:

```bash
./run/execute_runner terraform_dns apply
```

Records are defined in `terraform/dns/`:
- `infra.tf` - Infrastructure records
- `services.tf` - Application services
- `reverse_proxy.tf` - External-facing services

## Traffic Flow

### Internal Access

```
Client → Pi-hole (DNS) → bind9 → Service IP
```

### External Access (via Cloudflare Tunnel)

```
Internet → Cloudflare Edge → cloudflared (LXC 208) → nginx → Service
```

### Reverse Proxy Routes

All external traffic flows through nginx (LXC 110):

| Subdomain | Backend |
|-----------|---------|
| jellyfin.homelab.matagoth.com | 10.20.1.204:8096 |
| n8n.homelab.matagoth.com | 10.20.1.211:5678 |
| prometheus.homelab.matagoth.com | 10.20.1.210:9090 |
| ... | ... |

## Firewall Rules

### Container Isolation

- Containers use Proxmox bridge networking
- Inter-container traffic allowed on same bridge
- External traffic must go through nginx reverse proxy

### Key Ports

| Port | Service | Location |
|------|---------|----------|
| 22 | SSH | All containers |
| 53 | DNS | Pi-hole, bind9 |
| 80/443 | HTTP/HTTPS | nginx |
| 8006 | Proxmox UI | PVE host |

## VPN Configuration

The arrs stack uses WireGuard VPN via Gluetun:

```
┌────────────────────────────────────────────────────────┐
│                   dockerhost (LXC 205)                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │                    Gluetun                       │  │
│  │              (WireGuard VPN client)              │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐            │  │
│  │  │ Sonarr  │ │ Radarr  │ │qBittor- │            │  │
│  │  │         │ │         │ │  rent   │            │  │
│  │  └─────────┘ └─────────┘ └─────────┘            │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────┐
              │  VPN Provider    │
              │  (WireGuard)     │
              └──────────────────┘
                         │
                         ▼
              ┌──────────────────┐
              │    Internet      │
              └──────────────────┘
```

## Monitoring Network

```
┌─────────────────────────────────────────────────────────────┐
│                      Prometheus (LXC 210)                   │
│                        10.20.1.210                          │
└─────────────────────────────────┬───────────────────────────┘
                                  │ Scrapes metrics from:
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│ node_exporter │       │   Telegraf    │       │ Application   │
│ (containers)  │       │  (PVE host)   │       │   Metrics     │
│    :9100      │       │               │       │               │
└───────────────┘       └───────────────┘       └───────────────┘
```

## Adding New Network Resources

### New LXC Container

1. Choose IP from available range (10.20.1.212+)
2. Update LXC config with IP
3. Add DNS record in Terraform
4. Add reverse proxy entry if external access needed

### New Subnet

1. Configure on Proxmox bridge
2. Update firewall rules
3. Document in this file

## Troubleshooting

### Check Container Network

```bash
pct exec <vmid> -- ip addr
pct exec <vmid> -- ping 10.20.0.1
```

### DNS Resolution Test

```bash
dig @10.20.1.201 myservice.home.matagoth.com
nslookup myservice.home.matagoth.com 10.20.1.1
```

### Check Route to Container

```bash
ping 10.20.1.<id>
traceroute 10.20.1.<id>
```
