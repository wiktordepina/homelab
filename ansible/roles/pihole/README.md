# pihole

Pi-hole DNS sinkhole role.

## Description

This role installs and configures Pi-hole for network-wide ad blocking and DNS filtering.

## Tasks

- Installs Pi-hole and dependencies
- Configures upstream DNS
- Sets up web admin interface

## Requirements

- Debian-based OS

## Variables

None

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - pihole
```

## Ports

- `53` - DNS (TCP/UDP)
- `80` - Web admin interface

## Notes

Pi-hole acts as the primary DNS resolver for the network, blocking ads and tracking domains while forwarding legitimate queries to upstream resolvers.
