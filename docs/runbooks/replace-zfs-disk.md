# Replace a disk in the ZFS pool

The Proxmox host's bulk storage is a ZFS pool (`zpool`) with single-disk fault tolerance, currently RAIDZ1 across 7× 8 TB drives plus a dedicated SSD log device. When a disk fails or is failing, the pool stays online but in a degraded state until the disk is physically replaced and the new disk is resilvered into the array.

This runbook covers the replacement procedure end-to-end with the actual commands. The host needs to be physically accessible for the disk swap; everything else is done from a shell on the host. The pool was set up before this repository existed and is out of scope for IaC; the codeowner manages it directly.

## Before doing anything

Two things to check before opening the case.

**Is the disk actually failing?** A disk that has been kicked out of the pool can come back. Check the pool status; transient errors clear themselves on a scrub, persistent errors do not. Check the disk's SMART data for the underlying cause. A disk with a small number of read errors and no reallocations may simply have a flaky cable; reseating sometimes fixes it without a swap. A disk with growing reallocations or pending sectors needs to be replaced.

```bash
zpool status
smartctl -a /dev/disk/by-id/<failing-disk-id>
```

**Is a replacement on hand?** The pool is healthy in the degraded state for as long as no other disk fails. Resilver windows scale with pool size and can stretch into days for large pools, during which redundancy is reduced or absent. Replace as soon as a fresh disk is available; do not delay.

The replacement should match the existing disks in size and performance class. A larger disk is acceptable but its extra capacity is wasted until every disk in the pool is upgraded.

## 1. Identify the failing disk

ZFS reports disks by their stable identifier (`/dev/disk/by-id/...`) rather than their kernel-assigned device name. Always work in terms of the stable identifier — kernel device names like `/dev/sdd` can change between reboots, and using them produces incorrect commands that may target a different disk.

```bash
zpool status
```

A degraded pool with a faulted disk looks like this:

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
        logs
          ata-Samsung_SSD_870_EVO_250GB_S6PENM0TC05386X  ONLINE       0     0     0
```

Note the failing disk's identifier (the part starting `ata-...`). That string — not `/dev/sdX` — is what every subsequent command uses.

## 2. Physically replace the disk

1. Power down or hot-swap (depending on cage) and remove the failing disk.
2. Insert the replacement.
3. Confirm the kernel sees it and has assigned a stable identifier:

```bash
ls -l /dev/disk/by-id/ | grep -i <new-disk-serial>
```

Example output for a replacement drive:

```
lrwxrwxrwx 1 root root  9 May 26 13:02 ata-ST8000DM004-2U9188_ZR165ZXT -> ../../sdd
```

4. Verify the new drive's SMART health *before* committing it to the pool. A disk that arrived sick should go back to the supplier rather than into the array:

```bash
smartctl -a /dev/disk/by-id/ata-ST8000DM004-2U9188_ZR165ZXT
```

After insertion but before the replace command, the pool status shows the original disk as `UNAVAIL` with its old by-id path in a comment, and a numeric pool-side ID in place of the identifier:

```
        NAME                                             STATE     READ WRITE CKSUM
        zpool                                            DEGRADED     0     0     0
          raidz1-0                                       DEGRADED     0     0     0
            ...
            15001682754067572671                         UNAVAIL      0     0     0  was /dev/disk/by-id/ata-ST8000DM004-2U9188_ZR14QKCH-part1
            ...
```

## 3. Replace in ZFS

Use the pool's replace operation, naming the failed disk by its numeric pool-side ID (since the by-id path is no longer recognised) and the new disk by its stable identifier:

```bash
zpool replace zpool 15001682754067572671 /dev/disk/by-id/ata-ST8000DM004-2U9188_ZR165ZXT
```

The pool begins resilvering immediately. It stays online and serving reads and writes throughout, with reduced performance because the disks are also reading and writing for the resilver itself.

## 4. Monitor the resilver

Inspect status periodically. The resilver reports a percentage complete and an estimated time remaining; the estimate becomes more accurate as the resilver proceeds.

```bash
zpool status
```

Mid-resilver looks like this:

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
            ...
            replacing-5                                  DEGRADED     0     0     0
              15001682754067572671                       UNAVAIL      0     0     0  was /dev/disk/by-id/ata-ST8000DM004-2U9188_ZR14QKCH-part1
              ata-ST8000DM004-2U9188_ZR165ZXT            ONLINE       0     0     0  (resilvering)
            ...
```

To watch progress without re-running the command by hand:

```bash
watch -n 60 'zpool status | grep -A5 scan'
```

ZFS event log, useful when something else looks wrong during the resilver:

```bash
zpool events -v | tail -50
```

Expect the operation to take from hours to days depending on pool size. Rough guide for this hardware class:

| Pool size | Estimated resilver |
|-----------|--------------------|
| 10 TB     | 12–18 hours        |
| 20 TB     | 24–36 hours        |
| 40 TB     | 48–72 hours        |

The pool moves from `DEGRADED` to `ONLINE` once the resilver completes and ZFS confirms the new disk is fully synchronised. Until that happens, the pool tolerates *no* further disk failures.

## 5. After the resilver

Once `zpool status` reports `ONLINE` and the resilver line shows it completed:

```
  pool: zpool
 state: ONLINE
  scan: resilvered 7.45T in 1 day 12:34:56 with 0 errors
config:
        NAME                                             STATE     READ WRITE CKSUM
        zpool                                            ONLINE       0     0     0
        ...
```

Then:

- **Confirm zero errors on every disk** in the resilver report. Errors during resilver, on disks *other than* the one being replaced, indicate that another disk is failing and needs attention.
- **Run a scrub** at the next convenient time. The scrub is non-disruptive and confirms the entire pool is consistent. A scrub right after a resilver is occasionally useful for catching errors the resilver did not notice:

  ```bash
  zpool scrub zpool
  ```

- **File the failed disk** for warranty return, RMA, or destruction depending on the threat model. Do not return a disk that may contain sensitive data without first making it unreadable.

## Standing practice that reduces the surprise

The replacement procedure is a recovery; the practices that reduce how often it is needed are:

- **Regular scrubs.** A scheduled monthly or quarterly scrub catches latent errors before they accumulate into a disk eviction.
- **SMART monitoring.** A monitoring agent that reads SMART data and alerts on early indicators (reallocated sectors, pending sectors, ATA errors, read error rates) gives advance warning that a disk is on its way out.
- **Cold spares.** A spare disk on hand turns a multi-day "wait for delivery" into a same-day swap. For a single-tolerance pool, this is the difference between a calm replacement and a stressful one.
- **Pool health alerts via ZED.** The ZFS event daemon can be configured to send email when the pool changes state. Out of the box it is silent; the one-time configuration is in `/etc/zfs/zed.d/zed.rc`:

  ```bash
  ZED_EMAIL_ADDR="alerts@example.com"
  ZED_NOTIFY_VERBOSE=1
  ```

  Restart the daemon (`systemctl restart zfs-zed`) for the change to take effect.

## Related references

- [OpenZFS Documentation](https://openzfs.github.io/openzfs-docs/)
- [Proxmox ZFS Guide](https://pve.proxmox.com/wiki/ZFS_on_Linux)
