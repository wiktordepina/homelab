# Switch and access point

The managed switch and the wireless access point sit on the management LAN and together implement the VLAN topology that the upstream router (OPNsense) terminates. Neither device is configured by this repository; both are managed through their own web UIs. This document records the working state so that recovery from a factory reset, a firmware update gone wrong, or a hardware replacement does not depend on memory.

For the rationale on why these devices live outside IaC, and for the broader debt around this corner of the homelab, see [`.debt/switch-and-ap-config.md`](../../.debt/switch-and-ap-config.md). For the upstream router's view of the same VLANs, see [`.debt/opnsense-router.md`](../../.debt/opnsense-router.md).

## Hardware

- **Switch:** TP-Link TL-SG2008P. Eight Gigabit ports; ports 1–4 are PoE-capable. Hostname `switch.home.matagoth.com`, address `192.168.200.50` (DHCP-reserved on OPNsense).
- **Access point:** model not currently recorded. Hostname `accesspoint.home.matagoth.com`, address `192.168.200.60` (DHCP-reserved on OPNsense). Powered over Ethernet from the switch. Capturing the model is a small piece of outstanding debt; the IP and MAC are visible in the OPNsense DHCP map but the device's own UI is the canonical source for everything else.

Both devices' configuration lives only on the device itself. There is no exported configuration under version control. A periodic config export is captured as a resolution direction in the related debt note.

## VLANs

Three VLAN tags are in use across this fabric. The upstream router defines them; the switch and the AP must agree on the same numbers for the topology to function.

| Tag | Switch VLAN name | OPNsense interface | Subnet              | Purpose |
|-----|-------------------|--------------------|---------------------|---------|
| 1   | (default)         | `lan` / `igc0`     | `192.168.200.0/16`  | Management — switch, AP, Proxmox host |
| 10  | `Core`            | `opt4` / `vlan0.10`| `10.10.0.0/16`      | CORE — phones, laptops, consoles, the `gothnet` SSID |
| 50  | `IoT`             | `opt5` / `vlan0.50`| `10.50.0.0/16`      | IOT — TVs, smart bulbs, sensors, the `gothnet-iot` SSID |

The DMZ subnet (`10.20.0.0/16`, where the LXC fleet lives) and the DIRECT subnet (`10.100.0.0/16`, the wired desktop) do not traverse this switch. DMZ is a direct cable from the Proxmox host's `enp100s0` to OPNsense `igc1`; DIRECT is a direct cable from a workstation to OPNsense `igc2`.

## Port mapping

| Port | PoE | Connected device | Role |
|------|-----|------------------|------|
| 1    | yes | Access point     | Trunk: VLANs 10 and 50 tagged, VLAN 1 native (untagged). PoE-powered. |
| 2    | yes | Philips Hue hub  | Access on VLAN 50 (IOT). |
| 3    | yes | unused           | Default config (VLAN 1 untagged). |
| 4    | yes | PlayStation 5    | Access on VLAN 50 (IOT). |
| 5    | no  | unused           | Configured as access on VLAN 10 (CORE) but no device attached. |
| 6    | no  | Proxmox `enp99s0`| Trunk: VLANs 1, 10, 50 all tagged. The vantage point for L2 monitoring containers; see below. |
| 7    | no  | Proxmox `eno1`   | Access on VLAN 1 (management). The Proxmox host's management interface. |
| 8    | no  | OPNsense `igc0`  | Trunk: VLANs 10 and 50 tagged, VLAN 1 native (untagged). |

The two PoE-powered access ports for IoT devices (Hue hub on P2, PlayStation on P4) are conventional access ports — untagged member of VLAN 50, with VLAN 1 explicitly removed so the device cannot accidentally join the management VLAN.

## Trunk shapes

Two trunk shapes coexist on this switch, intentionally different.

The **classic trunk** carries VLAN 1 untagged (as the native VLAN) and VLANs 10 and 50 tagged. Port 1 (to the AP) and port 8 (to OPNsense) use this shape. It matches what OPNsense expects on its `lan` interface (`igc0` carries the management subnet without a tag) and what the AP expects so its own management traffic can flow.

The **all-tagged trunk** on port 6 carries VLANs 1, 10, and 50 all tagged, with no untagged native. This shape exists because the Proxmox-side bridge (`vmbr2`) is consumed by guests with explicit per-NIC VLAN tags — there is no host-originated traffic on this bridge that would benefit from a native VLAN. Symmetric tagging on both ends of the cable removes a class of confusion that arises when one end strips a tag the other end is asserting.

Access ports for IoT or CORE devices follow the same pattern as ports 2 and 4: untagged member of the relevant VLAN, with VLAN 1 explicitly removed.

## SSIDs and VLAN-to-SSID mapping

The access point exposes two SSIDs, mapped to two VLANs:

- `gothnet` — VLAN 10 (CORE).
- `gothnet-iot` — VLAN 50 (IOT).

Wireless clients on `gothnet` land on the CORE subnet; wireless clients on `gothnet-iot` land on IOT. The mapping is configured in the AP's UI and depends on the trunk on switch port 1 carrying both VLAN tags. A break in any one of the three places (AP SSID-to-VLAN map, switch port 1 trunk, OPNsense VLAN definition) silently moves wireless clients onto the wrong subnet.

## Recovery

Restoring either device from a factory reset is currently a UI exercise. The minimum set of facts a recovery procedure needs is what this document records:

- The VLAN tag numbers (10, 50) and their names.
- The trunk-port assignments (P1, P6, P8) and their respective shapes.
- The access-port assignments (P2, P4) and their VLAN.
- The SSID-to-VLAN mapping on the AP.
- Both devices' management addresses, so they are reachable to be reconfigured.

The credentials for both devices are kept in the operator's password manager. Periodic config exports are an open piece of debt — see the related debt note.
