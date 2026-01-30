# Replacing a Faulty Disk in ZFS Pool

> **Navigation:** [← Back to README](../README.md)

## Overview

This guide covers the process of replacing a failed disk in the ZFS storage pool. The homelab uses a RAIDZ1 configuration with 7x 8TB drives, providing single-disk fault tolerance.

## 1. Identify the Faulty Disk

First, check the pool status to identify the faulty disk:

```bash
zpool status
```

Example output showing a faulty disk:

```
  pool: zpool
state: DEGRADED
status: One or more devices are faulted in response to persistent errors.
        Sufficient replicas exist for the pool to continue functioning in a
        degraded state.
action: Replace the faulted device, or use 'zpool clear' to mark the device
        repaired.
config:
        NAME                                             STATE     READ WRITE CKSUM
        zpool                                            DEGRADED     0     0     0
          raidz1-0                                       DEGRADED     0     0     0
            ata-ST8000DM004-2U9188_ZR14PAGA              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14Q21Y              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14QGQY              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14QGVB              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14QGVX              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14QKCH              FAULTED      7 1.05K     0  too many errors
            ata-ST8000DM004-2U9188_ZR14QKVL              ONLINE       0     0     0
```

## 2. Physically Replace the Disk

1. Physically remove the faulty disk from the system
2. Insert the new replacement disk
3. After physical replacement, the pool status will show:

```
  pool: zpool
 state: DEGRADED
status: One or more devices could not be used because the label is missing or
        invalid.  Sufficient replicas exist for the pool to continue
        functioning in a degraded state.
action: Replace the device using 'zpool replace'.
   see: https://openzfs.github.io/openzfs-docs/msg/ZFS-8000-4J
  scan: scrub repaired 0B in 14:00:07 with 0 errors on Sun Mar  9 14:24:10 2025
config:

        NAME                                             STATE     READ WRITE CKSUM
        zpool                                            DEGRADED     0     0     0
          raidz1-0                                       DEGRADED     0     0     0
            ata-ST8000DM004-2U9188_ZR14PAGA              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14Q21Y              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14QGQY              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14QGVB              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14QGVX              ONLINE       0     0     0
            15001682754067572671                         UNAVAIL      0     0     0  was /dev/disk/by-id/ata-ST8000DM004-2U9188_ZR14QKCH-part1
            ata-ST8000DM004-2U9188_ZR14QKVL              ONLINE       0     0     0
        logs
          ata-Samsung_SSD_870_EVO_250GB_S6PENM0TC05386X  ONLINE       0     0     0
```

4. Identify the new disk's device name:

```bash
ls -l /dev/disk/by-id/ | grep ZXT
lrwxrwxrwx 1 root root  9 May 26 13:02 ata-ST8000DM004-2U9188_ZR165ZXT -> ../../sdd
```

## 3. Replace the Disk in ZFS

Use the `zpool replace` command:

```bash
zpool replace zpool 15001682754067572671 /dev/disk/by-id/ata-ST8000DM004-2U9188_ZR165ZXT
```

## 4. Monitor the Resilver Process

Check the progress of the resilver operation:

```bash
zpool status
```

Example output during resilver:

```
  pool: zpool
 state: DEGRADED
status: One or more devices is currently being resilvered.  The pool will
        continue to function, possibly in a degraded state.
action: Wait for the resilver to complete.
  scan: resilver in progress since Mon May 26 13:12:02 2025
        12.9T / 18.1T scanned at 11.0G/s, 179G / 17.9T issued at 153M/s
        25.6G resilvered, 0.98% done, 1 days 09:48:34 to go
config:

        NAME                                             STATE     READ WRITE CKSUM
        zpool                                            DEGRADED     0     0     0
          raidz1-0                                       DEGRADED     0     0     0
            ata-ST8000DM004-2U9188_ZR14PAGA              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14Q21Y              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14QGQY              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14QGVB              ONLINE       0     0     0
            ata-ST8000DM004-2U9188_ZR14QGVX              ONLINE       0     0     0
            replacing-5                                  DEGRADED     0     0     0
              15001682754067572671                       UNAVAIL      0     0     0  was /dev/disk/by-id/ata-ST8000DM004-2U9188_ZR14QKCH-part1
              ata-ST8000DM004-2U9188_ZR165ZXT            ONLINE       0     0     0  (resilvering)
            ata-ST8000DM004-2U9188_ZR14QKVL              ONLINE       0     0     0
        logs
          ata-Samsung_SSD_870_EVO_250GB_S6PENM0TC05386X  ONLINE       0     0     0
```

## 5. Verify Completion

After resilver completes, verify the pool is healthy:

```bash
zpool status
```

Expected output:

```
  pool: zpool
 state: ONLINE
  scan: resilvered 7.45T in 1 day 12:34:56 with 0 errors
config:
        NAME                                             STATE     READ WRITE CKSUM
        zpool                                            ONLINE       0     0     0
          raidz1-0                                       ONLINE       0     0     0
            ...all drives ONLINE...
```

## Best Practices

| Practice | Reason |
|----------|--------|
| **Always use device IDs** (`/dev/disk/by-id/`) | Device names (`/dev/sdX`) can change between reboots |
| **Keep spare drives** | Minimizes downtime during failures |
| **Regular scrubs** | Detects errors before they cause data loss |
| **Monitor SMART data** | Predicts failures before they happen |

## Monitoring Tips

### Watch Resilver Progress

```bash
watch -n 60 'zpool status | grep -A5 scan'
```

### Check ZFS Events

```bash
zpool events -v | tail -50
```

### SMART Health Check

Before installing a new drive, verify its health:

```bash
smartctl -a /dev/disk/by-id/ata-ST8000DM004-2U9188_ZR165ZXT
```

### Set Up Email Alerts

Configure ZFS Event Daemon (ZED) to send emails on pool events:

```bash
# Edit /etc/zfs/zed.d/zed.rc
ZED_EMAIL_ADDR="your@email.com"
ZED_NOTIFY_VERBOSE=1
```

## Estimated Resilver Times

| Pool Size | Estimated Time |
|-----------|----------------|
| 10 TB | 12-18 hours |
| 20 TB | 24-36 hours |
| 40 TB | 48-72 hours |

Times vary based on disk speed, system load, and data distribution.

## Related Documentation

- [OpenZFS Documentation](https://openzfs.github.io/openzfs-docs/)
- [Proxmox ZFS Guide](https://pve.proxmox.com/wiki/ZFS_on_Linux)
- [ZFS on Linux FAQ](https://openzfs.github.io/openzfs-docs/Getting%20Started/index.html)
