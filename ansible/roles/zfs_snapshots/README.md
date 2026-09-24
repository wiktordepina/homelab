# zfs_snapshots

Scheduled ZFS snapshots with count-based retention, per dataset, in one of two modes.

## Description

Installs a small script (`/usr/local/sbin/zfs-snapshots`) and a systemd timer that runs it every 15 minutes. For each dataset in `/etc/zfs-snapshots.conf`, the script takes a snapshot if one is due, then prunes all but the newest `keep`:

- **`on-change`**: a snapshot is due when anything has been written since the newest one: content, a new or deleted file, or a mode change. Retention is therefore the last `keep` *versions* of the dataset, however long ago they were made. Suits data that changes rarely and where every change matters, such as secrets.
- **`daily`**: a snapshot is due when there is none yet for the current UTC day, whether or not anything changed. Retention is the last `keep` *days*. Suits data that changes often, where "how it looked on a given day" is the useful recovery point, such as Terraform state.

Both are per dataset, not per file: an `on-change` dataset with `keep: 5` holds its last five states, which is the last five versions of a file only if nothing else in the dataset changed in between.

`on-change` datasets get `atime=off`. Under `relatime` a read still updates atime once a day, which would count as a change and push real versions out of retention on a dataset that is read on every CI job.

Snapshots are named `auto_<UTC timestamp>`. Only those are counted or pruned; hand-made snapshots on the same datasets are left alone. A change to the script or config triggers an immediate run during the converge.

Snapshots live on the same pool as the data. They cover a bad apply, a deleted file or a corrupted state file; they do not cover losing the pool.

## Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `zfs_snapshots_datasets` | ✅ | `[]` | List of `{name, mode, keep}`: the ZFS dataset (children not included), `on-change` or `daily`, and how many snapshots to retain |

## Dependencies

None. Runs on the PVE host, which has ZFS.

## Example usage

In `config/pve/playbook.yaml`:

```yaml
roles:
  - role: zfs_snapshots
    vars:
      zfs_snapshots_datasets:
        - name: zpool/secrets
          mode: on-change
          keep: 5
        - name: zpool/terraform
          mode: daily
          keep: 5
```

## Checking and restoring

List the snapshots for a dataset, oldest first:

```bash
./run/pve-ssh zfs list -t snapshot -o name,creation -s creation -r zpool/terraform
```

What did the last few runs do, and when is the next:

```bash
./run/pve-ssh 'systemctl list-timers zfs-snapshots.timer; journalctl -u zfs-snapshots.service -n 20 --no-pager'
```

Every snapshot is browsable read-only under the dataset's `.zfs/snapshot/` directory, so a single file can be compared or copied back without rolling anything back:

```bash
./run/pve-ssh
diff /zpool/secrets/.zfs/snapshot/<snapshot>/<file>.sh /zpool/secrets/<file>.sh
cp /zpool/terraform/.zfs/snapshot/<snapshot>/lxc-<vmid>.tfstate /zpool/terraform/lxc-<vmid>.tfstate
```

Secrets must stay `0644` after a copy back; the runner cannot read anything else.

Rolling a whole dataset back discards everything written since the snapshot, and `-r` also destroys every snapshot newer than it. Prefer the file copy above unless the whole dataset really is wrong:

```bash
zfs rollback -r zpool/terraform@<snapshot>
```
