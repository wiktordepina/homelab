# claude_workstation

Turns a VM into a host where Claude Code works unattended or from the phone, as an unprivileged user, under settings it cannot change. It works on forge repositories granted to the `matabot` account and on nothing hosted on GitHub.

## What lives where

| Path | Contents |
|------|----------|
| `/home/agent` | The `agent` user: Claude Code, uv, mise and mait-code under `~/.local/bin`, all installed as the agent so each can update itself |
| `/home/agent/work` | Checkouts the agent works in. The only place it may edit without a prompt |
| `/etc/claude-code/managed-settings.json` | Root-owned managed settings, templated from `claude_workstation_managed_settings` |
| `/usr/local/bin/fj`, `/usr/local/bin/yq` | Root-owned, pinned by version and checksum |
| `/etc/nftables.d/ingress.nft` | The inbound table; the outbound one is egress_proxy's |
| `/var/lib/maitre-d` | Home of the control service's account. maitre-d itself is not installed yet; `jobs/` and `snaps/` are where the session units read and write for it |
| `/etc/systemd/system/claude-{rc,job,snap}@.service` | The session units (see [Session units](#session-units)) |
| `/usr/local/libexec/claude-{job,trust}` | Root-owned helpers the units run |
| `/etc/polkit-1/rules.d/50-claude-units.rules` | What maitre-d may do to those units |
| `/run/claude-tmux` | The agent's tmux sockets, one per Remote Control server |

## The agent

`agent` has no sudo and no privileged group. The managed settings only bind because the agent cannot write `/etc`, so anything that gave it root, including membership of `docker`, would undo all of them. If containers are ever needed, they run rootless as the agent.

It reaches the forge over HTTP on Forgejo's own port as `matabot` (see [Network posture](#network-posture) for why not through the reverse proxy), with one token in `~/.git-credentials` (for git) and in fj's own key store. A token over HTTP rather than an SSH key means one credential and one revocation. There is no GitHub credential on the host at all.

`~/.ssh/id_ed25519` is generated for reading other guests through a restricted observer account. Nothing distributes it yet.

## Managed settings

| Setting | Why |
|---------|-----|
| `disableClaudeAiConnectors: true` | The subscription login brings the account's claude.ai connectors (Gmail, Drive, Calendar) into the agent, already connected. A session that has been steered by injected text could then read and send mail as the account holder, through endpoints any egress allowlist has to permit. A user-settings override does not bring them back. |
| `disableAutoMode: disable` | Sessions here are often half-attended from a phone. Auto mode is where Claude Code's own judgement replaces the human's, and until the egress fence enforces, nothing outside the session limits what that judgement can reach. |
| `permissions.disableBypassPermissionsMode: disable` | Rejects `--dangerously-skip-permissions`, and a subagent's `bypassPermissions`. |
| `allowManagedHooksOnly: true` | The agent writes freely under `~/work`, and that includes each repository's `.claude/settings.json`. A hook declared there would run commands with no prompt in the next session. Only the hooks below run. |
| `allowManagedPermissionRulesOnly: true` | The same path, for allow rules: a repository could otherwise widen the agent's own permissions. A session's "always allow" is therefore not saved. Everything not on the allow list prompts. |

The **hooks** are an audit hook and mait-code's own three, which `mait-code install` writes into the user settings, where the lock above ignores them. They are copied with mait-code's timeouts and with `async` on the observe hooks, so compaction and session exit do not wait for them. The audit hook sends every Bash command, with its session and working directory, to the journal before it runs:

```bash
journalctl -t claude-code-audit
```

The agent can also write to the journal under that tag, so treat the log as a record that cannot be erased, not as one that cannot be forged. When the pinned mait-code ref moves, compare `config/settings.json` at that ref with the three hooks declared in `defaults/main.yaml`.

The **allow list** is routine work that should not need a phone tap: reading and committing with git, `fj`, syncing and testing, mait-code's tools and read-only shell utilities. It is convenience and visibility, **not containment**, and no list of patterns could make it containment:

- Several entries run code the agent can write. `uv run pytest` runs `conftest.py`, `git commit` runs `.git/hooks`, and `git fetch --upload-pack=<command>` runs a command outright.
- Several read files the deny rules below name. `git diff --no-index /dev/null ~/.git-credentials` prints the forge token without a prompt.
- `git push *` includes rewriting history (`+refspec`, `--mirror`, deletes). What stops that reaching `main` is branch protection on the forge, where only `matagoth` merges and nobody pushes.

So an injected session can run code and read the bot's credentials without asking. The managed settings stop it **persisting** a wider grant for later sessions (hooks, allow rules, connectors, bypass and auto mode); they do not stop what a single session can do.

The **read denials** cover the forge token, SSH keys, Claude Code's own credentials and `.env` files. They stop the Read tool and plain shell reads such as `cat`. As above, they do not stop an allowed command or a program the agent writes, so they are a speed bump.

## Network posture

The host is fenced in both directions. The role depends on [egress_proxy](../egress_proxy/README.md), as the CI runners do, and adds an inbound table of its own.

**Observation first.** `claude_workstation_egress_enforce` starts `false`: squid allows every name and both tables accept, while keeping a record of what they would refuse. Until it is turned on, only PVE's own address is closed. Through squid the agent reaches anything else, including every UI nginx fronts, PVE's among them. The allowlist is built from the record (runbook: [post-deploy-setup](../../../docs/runbooks/post-deploy-setup.md#5-turn-the-egress-fence-on)). What follows describes the fence once it enforces.

**Out.** Squid on `127.0.0.1:3128` is the agent's only way out, and it decides by name. The proxy variables are set in the managed settings' `env` (for Claude Code and every command a session runs) and at the top of the agent's `.bashrc` (for SSH shells). A program that ignores them is refused rather than let round the proxy. Beyond that:

- **The forge** is reached through squid as `forge.home.matagoth.com:3000`, Forgejo's own address and port, which the firewall opens to squid alone. This is the runners' path. It is never reached through nginx, because squid only sees the name in a `CONNECT`, while nginx picks a site by SNI and `Host`: a tunnel opened for the forge's name could then ask nginx for any site it fronts. The forge's public URL is rewritten by git, so a clone URL copied from the web UI works as it is.
- **The rest of the LAN** is closed, nginx included. PVE's address is closed in observation mode too.
- **NTP** leaves directly, from the timesync user only. A VM keeps its own clock, and the pool servers are names that resolve anywhere.
- **root and `_apt`** go out directly, so converges and apt keep working. The agent has neither.

Squid refuses ports other than 80 and 443 (and the forge's) in observation mode as well, so a proxied request to any other port fails already, and shows as `TCP_DENIED` in squid's log.

**In.** `table inet ingress` (`/etc/nftables.d/ingress.nft`, loaded by `ingress-firewall.service`) allows SSH only from the addresses in `claude_workstation_ssh_sources`: the laptop and the desktop for hands-on sessions, the apply-runner range for converges, and PVE so `run/host-key-push` works after a rebuild. ICMP is allowed; everything else inbound is refused. Refusals are recorded as for the egress table:

```bash
./run/host-ssh 218 'nft list set inet ingress observed_input'
```

**Residuals**, beyond those the egress_proxy README lists:

- The agent can resolve any name, so DNS queries to the resolver carry data out a few bytes at a time.
- An allowlisted name that accepts uploads is a way out for whatever the agent can read. The forge is one, as `matabot`.
- The forge token crosses the DMZ in plain HTTP, as the runners' does.

The Bash sandbox is not used, so `bubblewrap` and `socat` are not installed.

## Session units

Three system template units with `User=agent`. They are system units rather than the agent's own, so the agent needs no linger and no user manager, and the unit files are not the agent's to change. The instance name is a checkout under `~/work` or a job id.

| Unit | What it runs |
|------|--------------|
| `claude-rc@<project>` | `claude remote-control --name <project> --spawn same-dir --capacity 2` in `~/work/<project>`, inside a tmux server of its own (`tmux -L <project>`). One shared tmux server would live in whichever unit started it first, and stopping that unit would end every project's session. |
| `claude-job@<id>` | One headless `claude -p --output-format json` run, for maitre-d's scheduler. |
| `claude-snap@<project>` | A one-shot `tmux capture-pane` of the project's Remote Control pane. maitre-d reads the text, but never gets the tmux socket, which would also let it type into the session. |

**Remote Control** servers listed in `claude_workstation_rc_projects` start at boot. Any other checkout can be started on demand. `remote-control` exits cleanly when the login has expired, so every exit is restarted after a minute; five within fifteen minutes leave the unit **failed**, which is the state to alert on. Taking a project off the list does not disable its unit; `systemctl disable claude-rc@<project>` does. A changed unit template reaches a running server only when it is restarted.

**Every checkout under `~/work` is trusted.** Remote Control stops at `Trust this folder? [y/N]` the first time it runs anywhere, so `claude-trust` marks the unit's own checkout as trusted in `~/.claude.json` before each start. Running Claude Code processes rewrite that file without the script's lock, so a write racing the start can in principle drop the flag. The server then sits at the prompt with the unit **active**, which a snapshot shows. Trust lets a repository's project settings take effect. The managed settings already ignore its hooks and permission rules. What trust still allows is the rest of the project settings, such as helper commands and `.mcp.json` servers. Since the agent can write those files itself, the boundary is what reaches `~/work` in the first place: repositories granted to `matabot`.

**Jobs** read their configuration from `/var/lib/maitre-d/jobs/<id>/`, a directory only maitre-d can open:

| File | Written by | Contents |
|------|------------|----------|
| `job.env` | maitre-d | `CLAUDE_JOB_PROJECT=<checkout>` |
| `prompt` | maitre-d | The prompt, sent on stdin |
| `result.json` | systemd, as root | Claude Code's JSON result, from stdout |

systemd reads the environment file and opens both stdio files as root before it drops to the agent. So the agent can neither read nor change its prompt on disk, nor rewrite its result afterwards. A job is limited by `RuntimeMaxSec` (2 hours), `MemoryMax` and `CPUQuota`; stopping the unit kills its whole cgroup. A run that hit a permission prompt still reports `"subtype": "success"`, with the refusal only in `permission_denials`, so maitre-d must treat any denial as needing attention.

**Snapshots** go to `/var/lib/maitre-d/snaps/<project>.txt`, written by systemd as root, so the agent cannot change a file once written. What goes into it is a different matter: the pane belongs to the agent, and any session can type into any project's tmux server, since they all run as the same user. Treat a snapshot as what the agent shows, not as evidence of what it did.

**maitre-d** may `start`, `stop`, `restart` and `reset-failed` units matching `claude-(rc|job|snap)@<name>.service`, and nothing else. `reset-failed` lets it clear a finished job once it has read the result, and recover a Remote Control server that hit its restart limit. It cannot enable or disable them, or touch any other unit. The polkit rule is the only thing it is delegated.

All three units run in `claude.slice`, which caps them together at 6G on top of each unit's 3G, and share one hardening block: `ProtectSystem=strict` with only the agent's home and the tmux directory writable, other homes hidden, a private `/tmp` and `/dev`, no capabilities and `NoNewPrivileges`. `systemd-analyze security` rates a job unit at 3.3 ("OK").

From the laptop, a Remote Control server's pane is one attach away. `TMUX_TMPDIR` is set in the agent's `.bashrc`:

```bash
./run/host-ssh 218
su - agent
tmux -L <project> attach
```

## Remote Control consent

`claude remote-control` asks `Enable Remote Control? (y/n)` on its first run and records the answer as `"remoteDialogSeen": true` in `~/.claude.json`. A unit with no terminal would block on that prompt, so the role merges the key into the file. This is not a documented setting; it was observed in testing. If a future Claude Code ignores it, a first manual run as the agent answers the prompt for good.

## Upgrading

- **Claude Code** updates itself, as the agent, in the background.
- **mait-code** is installed once at `claude_workstation_mait_code_ref`. To upgrade, bump the ref, then delete `~agent/.local/bin/mait-code` on the host and converge, which re-runs the bootstrap.
- **fj** and **yq**: bump the version and its `sha256` together. The checksum comes from the release artefact itself, so a version bump without a new checksum fails the download rather than installing something unverified.

## Rotating the forge token

Mint a new token and replace `MATABOT_FORGE_TOKEN` in `/pve/secrets/claude_workstation.sh` (see [post-deploy-setup](../../../docs/runbooks/post-deploy-setup.md#claude-code-workstation)). Then, on the host, remove fj's key store so the next converge writes the new token there too:

```bash
./run/host-ssh 218 'rm /home/agent/.local/share/forgejo-cli/keys.json'
```

Converge, then revoke the old token on the forge. `~/.git-credentials` is rewritten on every converge.
