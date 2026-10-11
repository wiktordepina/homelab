# maitre_d

Installs maitre-d, the workstation's control service, on the workstation VM: an MCP server over the agent's mait-code board, memories and reminders, and a web UI for them. It runs as its own user beside the agent and owns everything executive. What maitre-d does, its configuration and its CLI are in its own repository (`matagoth-zaibatsu/maitre-d`); this README covers how it is deployed.

Runs after [claude_workstation](../claude_workstation/README.md), which creates the `maitre-d` account, the session units maitre-d drives, and the firewall rules for its port.

## What lives where

| Path | Owner, mode | Contents |
|------|-------------|----------|
| `/opt/maitre-d/src` | root, under a `0750` root:maitre-d directory | The pinned release, a shallow clone |
| `/opt/maitre-d/venv` | root, as above | maitre-d and its locked dependencies |
| `/opt/maitre-d/bin/uv` | root | The role's own uv, pinned by version and checksum |
| `/etc/maitre-d/maitred.toml` | root:maitre-d `0640` | The config. The agent can read neither it nor the code |
| `/var/lib/maitre-d` | maitre-d `0700` | `maitred.db` (token and session hashes, the UI password hash), `mait-code/` (maitre-d's own mait-code setup and its model cache), `xdg/` (an empty config home) |
| `/etc/systemd/system/maitre-d.service` | root | The unit |

## Installing a release

`maitre_d_version` and `maitre_d_commit` pin a release tag on the forge. A converge clones the tag fresh when the checked-out commit differs, and fails if the tag does not point at the pinned commit. It then installs with `uv sync --frozen` against the system Python, and checks both `maitred version` and the running service's `/healthz` against the pin.

The clone uses `forge-deploy`'s read-only token from `/pve/secrets/maitre_d.sh`, through squid to the forge's own address. The token reaches git through its environment, never its arguments (the agent can read every process's command line) and never the remote URL (it would be saved in `.git/config`). Everything else the install fetches (PyPI, and mait-code's source on GitHub) goes out directly as root.

**mait-code moves in lockstep.** maitre-d imports mait-code and opens the agent's databases, and mait-code refuses a database on another schema version. The converge reads the mait-code release from maitre-d's `uv.lock` and fails unless it equals `claude_workstation_mait_code_ref`. To move to a maitre-d release that pins a newer mait-code, move both in one change.

## The agent's identity

The workstation agent's soul document, user context and communication style live in maitre-d's `identity/`, and the pinned release is their only source. The converge concatenates them, in that order and separated by a blank line, into Claude Code's managed memory at `/etc/claude-code/CLAUDE.md` (root, `0644`). It overwrites the file on every converge and never merges, the opposite of mait-code's installer. Managed memory loads first in every session, user settings cannot exclude it, and the agent cannot write it. The files are concatenated rather than `@`-imported because the docs do not say whether imports work from managed memory.

mait-code's own copies in the agent's data directory, which its `~/.claude/CLAUDE.md` imports, become one-line stubs pointing at the managed file. mait-code replaces an identity file only while it is byte-identical to a template it shipped, so its updates leave the stubs alone. `claude --safe-mode` would drop managed memory, so the managed settings deny the agent `claude` altogether (claude_workstation).

The installed file must equal the release's files:

```bash
./run/host-ssh 218 'cd /opt/maitre-d/src/identity && { cat soul_document.md; echo; cat user_context.md; echo; cat communication_style.md; } | cmp - /etc/claude-code/CLAUDE.md && echo identical'
```

## Reading the agent's data

The agent's `~/.claude/mait-code-data` and its databases belong to the `mait-data` group, which both maitre-d and the agent are in. Both, because whichever side opens a database first creates its `-wal` and `-shm` files as itself, and the other side then writes them through the group. The directory is setgid, so files the agent creates later join the group, and SQLite gives each database's `-wal` and `-shm` files the same mode and group as the database. A database the agent creates after a converge is readable but not writable by maitre-d until the next converge.

That reaches further than "reads the databases and writes the board". maitre-d, which faces the network, can create, replace or delete any file in that directory, including the Markdown that the agent's sessions load. And maitre-d parses SQLite files the agent controls completely. Both follow from the design: what limits them is maitre-d's own code and its login.

The unit hides every home directory behind a tmpfs and binds that directory back in, along with the work directory below. maitre-d sees nothing else of the agent's. Only a bound directory's own mode applies, because the tmpfs stands in for the homes above it.

## Listing the agent's projects

The sessions view lists projects as the folders under the agent's `~/work`, which the config passes as `work_dir`. The unit binds it read-only, and the role makes it `agent:mait-data 0740`. The group can read the directory but cannot search it.

The aim is not to hide the checkouts from maitre-d. The agent owns them, and maitre-d can already start a job that reads them. The point is that **maitre-d never resolves a path the agent controls**. A process with privileges the agent lacks, acting on paths in a directory the agent writes, is a confused deputy waiting to happen: a planted `~/work/foo -> /var/lib/maitre-d/maitred.db`, followed by mistake, lands in maitre-d's own writable data, and a read-only bind does not stop that. maitre-d gets the names and each entry's type from the directory listing (`os.scandir` with `is_dir(follow_symlinks=False)`, which does not stat) and nothing else. `Path.is_dir()` fails with `EACCES` here.

**The rule is enforced by maitre-d's code, not by the mode.** Without search permission the kernel resolves nothing below `~/work` for maitre-d, so as converged, a bug cannot follow a link there. But the agent owns `~/work` and its home, so it can widen the mode, or put a directory or symlink of its own choosing in `~/work`'s place, and systemd binds whatever is there on maitre-d's next start. Each converge restores the mode. Until then, the mode is hardening that the agent can undo. The agent's mait-code data directory has the same exposure, read-write, which is why maitre-d must also treat that directory's files as hostile.

The same rule settles two other points. maitre-d cannot tell a checkout from a stray folder, because stat-ing `<project>/.git` would need the search permission this withholds. And maitre-d never writes in `~/work`: cloning runs as the agent in a unit of its own. If the view ever needs more than names, such as branch or dirty state, a one-shot unit running as the agent should write a summary into maitre-d's directory, as the snapshots do, rather than maitre-d reaching in.

The directory is not setgid, so checkouts keep the agent's own group.

## Memory search

maitred embeds search queries with its own mait-code setup: its own data directory, where the model is cached, the agent's embedding provider and model (`maitre_d_embedding_provider`, `maitre_d_embedding_model`), and an empty `XDG_CONFIG_HOME`, so no mait-code settings file is read. The provider and model must match the agent's exactly, or search goes keyword-only. The converge downloads the model through squid before the first start, because maitred loads it before it listens.

## The unit

- `UMask=0077`: maitred's database files hold token and session hashes, and SQLite's `-wal` and `-shm` follow the umask.
- `MemoryMax` (2G) covers the embedding model and a password check, which takes about 128 MiB.
- Hardened: no capabilities, `ProtectSystem=strict`, every home hidden. **No `PrivatePIDs=` and no `ProtectProc=`**: the board shows a card's bound sessions, and mait-code checks them with `kill(pid, 0)` on the agent's processes. In another PID namespace every binding would read as dead.

## The network

maitred listens on the workstation's address, port `claude_workstation_service_port` (8790). The inbound table opens it to the reverse proxy alone, and the proxy's server block lets only the laptop and the desktop through (`allow` in the service catalogue). maitred's web UI accepts requests only from the proxy as a peer (`ui_peers`), so the agent is refused the port outright by an output rule on the workstation; see the claude_workstation README.

## After the first converge

Set the web UI password and mint the MCP clients' tokens: [post-deploy-setup](../../../docs/runbooks/post-deploy-setup.md#7-maitre-d).
