# base

Base system configuration role applied to LXC containers, VMs, and external hosts.

## Description

This role performs basic system setup that every host needs regardless of its purpose: OS package updates and disk reclamation, plus the `qemu-guest-agent` service on KVM guests so Proxmox-side `agent = 1` actually works. It should be included as the first role for any host.

## Tasks

- Clears the apt archive cache, then updates the apt cache and upgrades all installed packages. The clean happens before the download so the upgrade has maximum headroom on a small root disk.
- Removes superseded packages and purges their configuration. On KVM guests this is what drops old kernels; apt retains the booted kernel and the one before it.
- On KVM guests only (`ansible_virtualization_type == "kvm"`): installs `qemu-guest-agent` and enables the service. Skipped on LXCs and bare-metal hosts.

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
