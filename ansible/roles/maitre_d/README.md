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

## Reading the agent's data

The agent's `~/.claude/mait-code-data` and its databases belong to the `mait-data` group, which both maitre-d and the agent are in. Both, because whichever side opens a database first creates its `-wal` and `-shm` files as itself, and the other side then writes them through the group. The directory is setgid, so files the agent creates later join the group, and SQLite gives each database's `-wal` and `-shm` files the same mode and group as the database. A database the agent creates after a converge is readable but not writable by maitre-d until the next converge.

That reaches further than "reads the databases and writes the board". maitre-d, which faces the network, can create, replace or delete any file in that directory, including the Markdown that the agent's sessions load. And maitre-d parses SQLite files the agent controls completely. Both follow from the design: what limits them is maitre-d's own code and its login.

The unit hides every home directory behind a tmpfs and binds that one directory back in. maitre-d sees nothing else of the agent's.

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
