# Out-of-band access to the Proxmox host

The Proxmox host's Supermicro H11SSL-C carries an ASPEED AST2500 baseboard management controller — a small always-on computer on the motherboard, independent of the host operating system. It answers whether or not Proxmox is running, whether or not the host has booted, and even when the host is powered off but the PSU is still connected.

That makes it the tool of choice when the host is unreachable: power cycling, watching POST, editing BIOS, and reading fan and temperature sensors, all without physical access to the machine. This matters more once the host lives in a rack rather than on an open bench.

This runbook covers bringing the BMC onto the management network and using it. The package install and the BMC's own network settings are handled by the `ipmi` role in the PVE Extras playbook; everything here that is not covered by that role is covered below, and the reasons are given for the parts that are deliberately manual.

## What is already configured

| Property | Value |
|---|---|
| Address | `192.168.200.101` — `ipmi.home.matagoth.com` |
| Netmask / gateway | `255.255.0.0` / `192.168.200.1` |
| Address source | Static |
| Dedicated NIC MAC | `3c:ec:ef:47:b0:49` |
| LAN mode | `02` — failover |
| Web UI | `https://192.168.200.101` |
| RMCP+ | UDP 623 |

The address is static rather than DHCP-reserved on purpose. Out-of-band access has to work precisely when the things that hand out leases are themselves the problem — a BMC that depends on OPNsense being healthy is not much use when OPNsense is what you are trying to fix.

## Shared, dedicated, and failover

The board has three network paths for the BMC, selected by a mode setting:

- **Dedicated (`00`)** — the BMC uses its own physical RJ45, separate from the host's NICs. Genuinely out-of-band: the host's network stack, bridge configuration and NIC driver are all irrelevant to whether you can reach it.
- **Shared (`01`)** — the BMC piggybacks on onboard LAN1 (`eno1`). One cable, but BMC reachability now depends on that port.
- **Failover (`02`)** — dedicated if the dedicated port has link, otherwise shared. This is the shipped default and the current setting.

Because the mode is failover and nothing is plugged into the dedicated port, **the BMC currently answers over `eno1`** — the same cable that carries Proxmox management traffic to switch port 7. This works, and needed no new cabling.

It is not the end state. Sharing means a broken bridge configuration, a NIC driver problem, or a mistaken `ifdown` can take the BMC away at exactly the moment it is needed. Wiring the dedicated port restores true out-of-band access; failover mode then uses it automatically with no configuration change.

Read the current mode:

```bash
ipmitool raw 0x30 0x70 0x0c 0
```

Returns ` 00`, ` 01` or ` 02`. Leave it at `02` — failover is strictly better than pinning to dedicated, because it degrades to the shared path rather than going dark if the dedicated cable is disturbed.

## Wiring the dedicated port

Switch port 3 is free, PoE-capable, and already an untagged member of VLAN 1 (management). No switch reconfiguration is needed — see [switch-and-ap](../reference/switch-and-ap.md).

1. Locate the dedicated IPMI RJ45 on the rear I/O. On the H11SSL-C it is the RJ45 physically separated from the LAN1/LAN2 pair, nearest the USB stack.
2. Patch it to switch port 3.
3. Confirm the BMC moved to the dedicated NIC — the MAC stays the same, so verify by link rather than by address:

```bash
ipmitool lan print 1 | grep -i "MAC Address"
```

Reachability should be unbroken across the change; the address does not move.

**Keep the BMC on the management VLAN only.** BMC firmware has a long history of serious vulnerabilities, is rarely patched, and should never be routable from the internet or from the IOT or CORE subnets. Untagged VLAN 1 is correct.

## Everyday use

All remote commands need credentials for a BMC user account. Substitute `<user>` throughout.

```bash
# Sensors — fans, temperatures, voltages, without lm-sensors on the host
ipmitool -I lanplus -H ipmi.home.matagoth.com -U <user> -P '<password>' sdr

# Power state
ipmitool -I lanplus -H ipmi.home.matagoth.com -U <user> -P '<password>' chassis power status

# Power control. `soft` asks the OS to shut down; `off` cuts power immediately
# and is the equivalent of holding the button in.
ipmitool -I lanplus -H ipmi.home.matagoth.com -U <user> -P '<password>' chassis power on
ipmitool -I lanplus -H ipmi.home.matagoth.com -U <user> -P '<password>' chassis power soft
ipmitool -I lanplus -H ipmi.home.matagoth.com -U <user> -P '<password>' chassis power reset

# Serial-over-LAN — a console without a monitor. Escape with `~.`
ipmitool -I lanplus -H ipmi.home.matagoth.com -U <user> -P '<password>' sol activate
```

Locally on the host, no credentials or network are needed — these go over the KCS interface:

```bash
ipmitool mc info
ipmitool lan print 1
ipmitool sdr
```

That local path is the recovery route. A BMC misconfigured to an unreachable address is always fixable from a host shell, which is why the `ipmi` role can set the BMC's address without risk of locking itself out.

For full graphical console — BIOS access, watching POST, mounting virtual media — use the web UI at `https://192.168.200.101`. The certificate is self-signed and the warning is expected.

## User accounts

Not managed by the role. Account changes carry lockout consequences and are a deliberate, occasional act rather than something a playbook should reconcile on every run.

```bash
ipmitool user list 1
```

Two accounts matter on this board:

- **`ADMIN` (ID 2)** — the Supermicro factory account, shipped enabled with `ADMINISTRATOR` privilege. It should be disabled once a named account exists, since a default-named administrator on a device with weak firmware is exactly the wrong thing to leave enabled.
- **A named account** — the account actually used day to day.

Disable the factory account, having first confirmed the named account works remotely:

```bash
ipmitool user disable 2
```

Change a password:

```bash
ipmitool user set password <user-id>
```

Do not disable an account until you have proved the replacement works over the network. The local KCS path can re-enable it, but only from a host shell — which is unavailable in precisely the scenario the BMC exists to solve.

## Troubleshooting

**No `/dev/ipmi0`.** The KCS interface is not being probed. Check `dmesg | grep -i ipmi` for `IPMI message handler: interfacing existing BMC`. If absent, load the modules with `modprobe ipmi_si ipmi_devintf`.

**Ping works, `ipmitool -I lanplus` does not.** Almost always credentials rather than networking. The error `Unable to establish IPMI v2 / RMCP+ session` with a known-bad username confirms the service is listening and rejecting properly.

**Nothing responds after a firmware update or a BMC reset.** The BMC can drop to defaults. Re-read the configuration locally with `ipmitool lan print 1` and re-run the PVE Extras playbook, which will restore the addressing.

**Cold-reset the BMC** without touching the host — the host keeps running throughout:

```bash
ipmitool mc reset cold
```
