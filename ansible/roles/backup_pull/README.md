# backup_pull

Pulls encrypted backup archives from guests onto the zpool, verifies each one, keeps the newest few, and alerts when a pull fails.

## Description

Runs on the PVE host. A daily timer runs `/usr/local/sbin/backup-pull`. For each job in `/etc/backup-pull.conf` it:

1. SSHes to the guest as root, with the PVE key Terraform seeds into every guest, and streams the archive. The remote side refuses a **missing** archive, and an archive **older than `max_age_hours`**, so a backup job that has quietly stopped on the guest is reported here instead of the same old archive being pulled forever.
2. Decrypts the pull with the job's age identity into a root-only file under `/run` (tmpfs), checks that it is a sound, non-empty zip, and deletes the plaintext.
3. Stores it as `/zpool/backups/<name>/<name>-<UTC timestamp>.zip.age` (mode `0600`) and prunes all but the newest `keep`.

Any failed job posts a high-priority message to the `homelab-alerts` ntfy topic, straight at the ntfy container rather than through DNS and the reverse proxy. The run carries on with the other jobs and exits non-zero at the end. A change to the script or config triggers an immediate run during the converge.

The direction is deliberate. The guest publishes an archive and the hypervisor fetches it, so the guest never holds a credential that reaches PVE.

The archives live on the same pool as everything else. They cover losing or rebuilding a guest; they do not cover losing the pool.

## Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `backup_pull_jobs` | ✅ | `[]` | List of `{name, host, path, max_age_hours, keep, age_identity}`, described below |
| `backup_pull_dataset` | | `zpool/backups` | Dataset the archives are stored under, created if missing |
| `backup_pull_schedule` | | `*-*-* 04:00:00` | systemd `OnCalendar` for the pull. Leave room after the guests' own backup times |
| `backup_pull_ntfy_url` | | `http://10.20.1.202` | ntfy base URL for alerts |
| `backup_pull_ntfy_topic` | | `homelab-alerts` | ntfy topic for alerts |

Each job:

- `name` is the directory and file prefix under the dataset (`[a-z0-9-]`).
- `host` is the guest's address.
- `path` is the absolute path of the encrypted archive on the guest.
- `max_age_hours` is how old the archive may be before the pull reports the guest's backup job as stopped. Set it a little over the guest's backup interval.
- `keep` is how many pulled archives to retain.
- `age_identity` is the private key used to verify each pull decrypts, normally under `/zpool/secrets/`.

Alerts authenticate with `NTFY_CREDS` from `/zpool/secrets/ntfy.sh`.

## Dependencies

None. Runs on the PVE host, which has ZFS. It installs `age`.

## Example usage

In `config/pve/playbook.yaml`:

```yaml
roles:
  - role: backup_pull
    vars:
      backup_pull_jobs:
        - name: hermes
          host: 10.20.1.217
          path: /var/lib/hermes-backup/hermes.zip.age
          max_age_hours: 26
          keep: 14
          age_identity: /zpool/secrets/hermes-backup.agekey
```

## Checking

What is stored, newest last:

```bash
./run/pve-ssh 'ls -l /zpool/backups/hermes/'
```

What the last run did, and when the next one is:

```bash
./run/pve-ssh 'systemctl list-timers backup-pull.timer; journalctl -u backup-pull.service -n 20 --no-pager'
```

Run a pull now:

```bash
./run/pve-ssh 'systemctl start backup-pull.service; journalctl -u backup-pull.service -n 5 --no-pager'
```

## After rebuilding a guest

The guest comes back with a new SSH host key. PVE's `known_hosts` still holds the old one, so the next pull fails with an alert saying it could not SSH to the host. Clear the old key before the pull runs (the same step `./run/host-key-push` needs):

```bash
./run/pve-ssh 'ssh-keygen -f /root/.ssh/known_hosts -R <guest-ip>'
```

The first pull after that trusts the new key.

A rebuilt guest also takes a fresh backup of its empty state during the converge, and the next pull stores it. The older archives are still there, up to `keep` of them, so restore from one of those rather than the newest.
