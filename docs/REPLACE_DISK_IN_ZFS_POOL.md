# Replacing a Faulty Disk in ZFS Pool

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

## Notes:
- Always use device IDs (/dev/disk/by-id/) instead of device names (/dev/sdX) when replacing disks
- The pool will remain in DEGRADED state until the resilver process completes
- The system remains operational during the resilver process
- Resilver time depends on pool size and system performance
