# bluetooth_host

Loads the kernel modules a Bluetooth USB dongle needs on the Proxmox host, so guest LXCs with USB pass-through can drive the radio.

## Description

The Bluetooth subsystem is a kernel-level concern: the `bluetooth` core module exposes the `AF_BLUETOOTH` socket family, and `btusb` is the driver that recognises USB BT adapters and creates `hciN` interfaces. Both have to be loaded on the **hypervisor**; a privileged guest container can use them, but cannot load them itself.

This role makes both modules load on every boot via `/etc/modules-load.d/bluetooth.conf`, and loads them immediately on first apply so the change takes effect without a reboot.

The role does **not** install BlueZ on the host — `bluetoothd` runs inside the consumer LXC (currently `switchbot-bridge`, VMID 214) and talks to the kernel directly. Keeping the userland out of the hypervisor preserves the "host is a hypervisor, not a service host" model in the [architecture](../../../docs/concepts/architecture.md).

## Tasks

- Templates `/etc/modules-load.d/bluetooth.conf` listing `bluetooth` and `btusb` for boot-time loading.
- `modprobe`s both modules immediately so the guest can use BT without waiting for a host reboot.

## Requirements

- Runs on the Proxmox host (target of `ansible_pve`).
- A USB Bluetooth dongle plugged into the host. The role does not check that one is present; if no dongle is plugged in, the modules load harmlessly and `hci0` simply does not appear.

## Variables

None.

## Dependencies

None. Intentionally minimal — this is a one-shot kernel-module concern.

## Example Usage

This role is applied via the PVE playbook only; it is not used inside containers.

```yaml
# config/pve/playbook.yaml
- name: PVE Extras
  hosts: 192.168.200.100
  roles:
    - telegraf
    - bluetooth_host
```

Apply with `./run/execute_runner ansible_pve` (runner-side; not from a developer laptop).

## Verifying

After apply, on the Proxmox host:

```bash
lsmod | grep -E '^bluetooth|^btusb'   # both should be listed
ls /proc/net/bluetooth                # directory should exist
hciconfig                             # should show hci0 if a dongle is plugged in
```

Inside the consumer LXC (e.g. 214) the AF_BLUETOOTH socket family becomes usable on the next `bluetoothd` retry; no container restart is needed.

## Notes

- USB pass-through into the consumer LXC is configured per-container in `pve_extra` (cgroup `c 189:* rwm` plus a bind of `/dev/bus/usb`), not here. This role is purely about the kernel side.
- The Bluetooth subsystem cannot be made available to **unprivileged** containers by loading modules alone — that needs capability remapping and is a separate concern. Today's only consumer (214) is privileged.
