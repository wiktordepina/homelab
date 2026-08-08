# ipmi

Baseboard management controller (BMC) access for the Proxmox host.

## Description

This role installs `ipmitool` and brings the BMC's own network configuration into the management subnet, so the host can be reached out-of-band — powered on, powered off, and driven through BIOS — without physical access to it.

The BMC is a small always-on computer on the motherboard, independent of the host operating system. It answers whether or not Proxmox is running, and it keeps its network settings in baseboard firmware, so they survive a host reinstall and are *not* configured through `/etc/network/interfaces`.

## Tasks

- Installs `ipmitool`
- Reads the BMC's current LAN configuration over the local KCS interface
- Sets the BMC address source, address, netmask and gateway where they differ

## Requirements

- A board with a BMC exposing a KCS interface (`/dev/ipmi0`)
- The `ipmi_si` and `ipmi_devintf` kernel modules, which Debian loads automatically when the interface is advertised via SMBIOS or ACPI

## Notes

Every task talks to the BMC over the local KCS interface rather than over the network. The role can therefore set the BMC's own address without needing to reach it first, and cannot lock itself out by getting that address wrong — a bad value is always recoverable from the host itself.

The role deliberately does not manage BMC user accounts or the dedicated/shared LAN mode. Both are one-time decisions with lockout consequences, and both are covered in the [out-of-band access runbook](../../../docs/runbooks/ipmi-out-of-band-access.md).
