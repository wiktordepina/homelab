# Upgrade Jellyfin across a major version

A patch bump of Jellyfin is an ordinary converge: change the URLs, apply, done. A major version (10.x to 12.x, for example) can carry one-way database migrations that run on the first start, take several minutes, and must not be interrupted. Once they have run, the only way back is a restore. This runbook wraps the converge in the steps that make that safe.

Jellyfin runs on LXC 204. The role installs three packages from URLs pinned in `ansible/roles/jellyfin/vars/main.yml`: `jellyfin-ffmpeg<N>`, `jellyfin-server` and `jellyfin-web`.

## 1. Read the release notes

Read the notes for the target release and every major release in between, on [the Jellyfin releases page](https://github.com/jellyfin/jellyfin/releases). Look for:

- the supported direct upgrade path (some majors require an intermediate release first);
- the FFmpeg major the release needs, which decides the `jellyfin-ffmpeg<N>` package;
- plugin and username requirements;
- steps required after the upgrade, such as a full library scan.

## 2. Bump the pinned packages

Edit the three URLs in `ansible/roles/jellyfin/vars/main.yml` together. Check that each one resolves before committing; Jellyfin removes old builds, so a URL that worked once can 404 later:

```bash
for u in $(yq -r '.[]' ansible/roles/jellyfin/vars/main.yml); do
  curl -sIL -o /dev/null -w "%{http_code} $u\n" "$u"
done
```

Every line should start with `200`. Merge through a PR as usual.

## 3. Pre-flight on 204

Run these before the converge. Each one is read-only or reversible.

Check that no two usernames differ only by case (Jellyfin 12 rejects them):

```bash
./run/host-ssh 204 'python3 -c "import sqlite3; c = sqlite3.connect(\"file:/var/lib/jellyfin/data/jellyfin.db?mode=ro\", uri=True); print(c.execute(\"select lower(Username), count(*) from Users group by lower(Username) having count(*) > 1\").fetchall())"'
```

Expected output: `[]`. Anything else names a clash to rename in the dashboard first.

List the installed plugins, so you know what to reinstall afterwards:

```bash
./run/host-ssh 204 ls /var/lib/jellyfin/plugins
```

## 4. Back up and remove plugins

Stop the service, then take a full backup of the data and config directories. The backup stays on 204's root disk, which has plenty of room:

```bash
./run/host-ssh 204 systemctl stop jellyfin
./run/host-ssh 204 'tar -C / -czf /root/jellyfin-backup-$(date +%F).tar.gz var/lib/jellyfin etc/jellyfin && ls -lh /root/jellyfin-backup-*.tar.gz'
```

Move every installed plugin aside. `configurations/` stays where it is, so each plugin picks its settings back up when it is reinstalled:

```bash
./run/host-ssh 204 'd=/root/jellyfin-plugins-$(date +%F); mkdir -p "$d" && find /var/lib/jellyfin/plugins -mindepth 1 -maxdepth 1 -type d ! -name configurations -exec mv -t "$d" {} + && ls /var/lib/jellyfin/plugins "$d"'
```

Leave the service stopped. The server package's install script starts it.

## 5. Converge

Dispatch the LXC workflow for 204 from `main`:

```bash
gh workflow run _lxc.yml --ref main -f vmid="204 - jellyfin" -f tf_action=apply
gh run watch "$(gh run list --workflow=_lxc.yml --limit 1 --json databaseId -q '.[0].databaseId')"
```

The role installs ffmpeg first, then the server, whose install script starts Jellyfin, and then the web client. Its handler only makes sure the service is running and never restarts it, so the converge cannot interrupt the migrations.

## 6. Let the migrations finish

Follow the log until the server reports it has started:

```bash
./run/host-ssh 204 journalctl -u jellyfin -f
```

Do not restart the service while the migrations are running. When they are done, check the version:

```bash
./run/host-ssh 204 'dpkg-query -W jellyfin-server jellyfin-web "jellyfin-ffmpeg*"'
```

## 7. After the upgrade

- Sign in to https://jellyfin.homelab.matagoth.com with an existing account; users and settings should be intact.
- Run a full library scan: Dashboard -> Libraries -> Scan All Libraries. Some majors require it.
- Reinstall the plugins from step 3 through Dashboard -> Plugins -> Catalog, then restart Jellyfin from the dashboard once.
- Once you are happy, delete `/root/jellyfin-backup-*.tar.gz` and `/root/jellyfin-plugins-*` on 204.

## Rolling back

Migrations cannot be reversed in place. Restore the backup, then pin the previous release again:

```bash
./run/host-ssh 204 systemctl stop jellyfin
./run/host-ssh 204 'rm -rf /var/lib/jellyfin /etc/jellyfin && tar -C / -xzf /root/jellyfin-backup-<date>.tar.gz'
```

Revert the URL bump in a PR, merge it and converge 204 again. If the old server version is lower than the one now installed, dpkg refuses the downgrade. Install the old packages by hand before the converge:

```bash
./run/host-ssh 204 'cd /tmp && curl -fLO <old-server-url> && curl -fLO <old-web-url> && apt-get install -y --allow-downgrades ./jellyfin-server_*.deb ./jellyfin-web_*.deb'
```
