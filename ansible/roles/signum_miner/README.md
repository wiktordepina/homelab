# signum_miner

Signum cryptocurrency miner role.

## Description

This role installs and configures a Signum (formerly Burstcoin) plot miner.

## Tasks

- Installs miner software
- Configures plot directories
- Sets up mining service

## Requirements

- Debian-based OS
- Plot storage mounted

## Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `signum_miner_plot_dirs` | ✅ | - | List of directories containing plot files |

## Dependencies

- `base`

## Example Usage

```yaml
pve_extra:
  - mp0: /mnt/pve/Plot0/plots,mp=/mnt/plots0,backup=0
  - mp1: /mnt/pve/Plot1/plots,mp=/mnt/plots1,backup=0
  - mp2: /mnt/pve/Plot2/plots,mp=/mnt/plots2,backup=0

ansible:
  roles:
    - base
    - role: signum_miner
      vars:
        signum_miner_plot_dirs:
          - /mnt/plots0
          - /mnt/plots1
          - /mnt/plots2
```

## Templates

- Miner configuration templates

## Notes

The miner scans pre-generated plot files to participate in Signum's proof-of-capacity mining.
