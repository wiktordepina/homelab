# base

Base system configuration role applied to LXC containers, VMs, and external hosts.

## Description

This role performs basic system setup that every host needs regardless of its purpose: OS package updates, unattended security updates between converges, disk reclamation and a journald size cap, plus the `qemu-guest-agent` service on KVM guests so Proxmox-side `agent = 1` actually works. It should be included as the first role for any host.

## Tasks

- Clears the apt archive cache, then updates the apt cache and upgrades all installed packages. The clean happens before the download so the upgrade has maximum headroom on a small root disk.
- Removes superseded packages and purges their configuration. On KVM guests this is what drops old kernels; apt retains the booted kernel and the one before it.
- Installs `unattended-upgrades` and enables the daily apt timers, so Debian security updates land between converges rather than only when a converge is dispatched. A drop-in (`/etc/apt/apt.conf.d/51homelab-unattended-upgrades`) clears the packaged origins list and keeps only the `-security` suite, because the packaged list also includes the main archive's point releases. Automatic reboot stays off; a host that needs a reboot after a kernel or libc update waits for one. Services whose package takes a security update are restarted by the package itself, so daemons such as nginx, squid, sshd and mosquitto can restart between converges. A security fix in a shared library such as OpenSSL is different: it lands on disk, but the daemons linked against it keep the old copy loaded until something restarts them. The downloaded packages are cleared weekly, so the archive cache does not grow between converges on a small root disk.
- This role's apt tasks wait up to `base_apt_lock_timeout` seconds for the dpkg lock, so a converge that starts during an unattended run waits for it instead of failing. Apt tasks in other roles keep the module's default.
- Caps the systemd journal at 200M through a drop-in in `/etc/systemd/journald.conf.d/`, restarting journald when it changes. The default ceiling is 10% of the filesystem, which is too generous on a small root disk.
- On KVM guests only (`ansible_virtualization_type == "kvm"`): installs `qemu-guest-agent` and enables the service. Skipped on LXCs and bare-metal hosts.

## Requirements

- Debian-based OS (Debian, Ubuntu)
- Root/sudo access

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `base_apt_lock_timeout` | `900` | Seconds each of this role's apt tasks waits for the dpkg lock |

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
