# Replace a disk in the ZFS pool

The Proxmox host's bulk storage is a ZFS pool with single-disk fault tolerance. When a disk fails or is failing, the pool stays online but in a degraded state until the disk is physically replaced and the new disk is resilvered into the array.

This runbook covers the replacement procedure. The host needs to be physically accessible for the disk swap; everything else is done from a shell on the host.

## Before doing anything

Two things to check before opening the case.

**Is the disk actually failing?** A disk that has been kicked out of the pool can be back. Check the pool status; transient errors clear themselves on a scrub, persistent errors do not. Check the disk's SMART data for the underlying cause. A disk with a small number of read errors and no reallocations may simply have a flaky cable; reseating sometimes fixes it without a swap. A disk with growing reallocations or pending sectors needs to be replaced.

**Is a replacement on hand?** The pool is healthy in the degraded state for as long as no other disk fails. Resilver windows scale with pool size and can stretch into days for large pools, during which redundancy is reduced or absent. Replace as soon as a fresh disk is available; do not delay.

The replacement should match the existing disks in size and performance class. A larger disk is acceptable but its extra capacity is wasted until every disk in the pool is upgraded.

## Identify the disk to replace

ZFS reports disks by their stable identifier rather than their kernel-assigned device name. Inspect the pool status to find the failing disk's identifier, and note it. The identifier is a string starting with the bus type and including the disk model and serial number.

Always work in terms of the stable identifier. Kernel-assigned device names can change between reboots, and using them produces incorrect commands that may target a different disk.

## Physically replace the disk

Remove the failing disk from the host's drive bay and insert the replacement. After insertion, confirm the new disk is visible to the kernel and has a stable identifier. Verify its SMART health before proceeding; a new disk that arrived sick should go back to the supplier rather than into the pool.

The pool's status, after insertion but before the replace command, will show the original disk as unavailable and the new disk as a present-but-unused device.

## Replace in ZFS

Use the pool's replace operation, naming the failed disk by its identifier (or its numeric pool-side ID if the original identifier is no longer recognised) and the new disk by its stable identifier. The pool begins resilvering immediately.

Resilver runs in the background. The pool stays online and serving reads and writes throughout, with reduced performance because the disks are also reading and writing for the resilver itself.

## Monitor the resilver

Inspect the pool's status periodically to check progress. The resilver reports a percentage complete and an estimated time remaining; the estimate becomes more accurate as the resilver proceeds. Expect the operation to take from hours to days depending on pool size and load.

The pool moves from degraded to online once the resilver completes and ZFS confirms the new disk is fully synchronised. Until that happens, the pool tolerates *no* further disk failures.

## After the resilver

Once the pool reports online and the resilver is complete:

- Confirm there are zero read, write, or checksum errors on every disk. Errors during resilver, on disks other than the one being replaced, indicate that another disk is failing and needs attention.
- Run a scrub at the next convenient time. The scrub is non-disruptive and confirms the entire pool is consistent. A scrub right after a resilver is occasionally useful for catching errors the resilver did not notice.
- File the failed disk for warranty return, RMA, or destruction depending on the threat model. Do not return a disk that may contain sensitive data without first making it unreadable.

## Standing practice that reduces the surprise

The replacement procedure is a recovery; the practices that reduce how often it is needed are:

- **Regular scrubs.** A scheduled monthly or quarterly scrub catches latent errors before they accumulate into a disk eviction.
- **SMART monitoring.** A monitoring agent that reads SMART data and alerts on early indicators (reallocated sectors, pending sectors, ATA errors, read error rates) gives advance warning that a disk is on its way out.
- **Cold spares.** A spare disk on hand turns a multi-day "wait for delivery" into a same-day swap. For a single-tolerance pool, this is the difference between a calm replacement and a stressful one.
- **Pool health alerts.** The ZFS event daemon can be configured to send alerts when the pool changes state. Out of the box it is silent; configuring the alert path is a one-time job worth doing.

These belong in the homelab's monitoring story rather than in this runbook; the runbook is what to do when prevention has not been enough.
