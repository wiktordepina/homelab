# ntfy

ntfy push notification server role.

## Description

This role installs and configures ntfy, a simple HTTP-based pub-sub notification service.

## Tasks

- Installs ntfy server
- Configures server settings
- Sets up systemd service

## Requirements

- Debian-based OS

## Variables

Refer to `vars/main.yaml` for configuration options.

## Dependencies

- `base`

## Example Usage

```yaml
ansible:
  roles:
    - base
    - ntfy
```

## Templates

- Configuration templates in `templates/`

## Files

- Service configuration files

## Handlers

- Service restart handlers

## Usage

Once deployed, ntfy can receive notifications via HTTP:

```bash
curl -d "Deployment complete" http://ntfy.home.matagoth.com/alerts
```

## Notes

ntfy is used for CI/CD notifications and system alerts. The `runner-toolbox` includes helper functions for sending notifications.
