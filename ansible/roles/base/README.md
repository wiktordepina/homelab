# base

Base system configuration role applied to all LXC containers.

## Description

This role performs basic system setup including OS package updates. It should be included as the first role for all containers.

## Tasks

- Updates apt cache
- Upgrades all installed packages

## Requirements

- Debian-based OS (Debian, Ubuntu)
- Root/sudo access

## Variables

None

## Dependencies

None

## Example Usage

```yaml
ansible:
  roles:
    - base
```

## Notes

This role should always be the first role applied to ensure the system is up to date before installing additional software.
