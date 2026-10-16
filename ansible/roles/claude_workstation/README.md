# claude_workstation

Turns a VM into a host where Claude Code works unattended or from the phone, as an unprivileged user, under settings it cannot change. It works on forge repositories granted to the `matabot` account and on nothing hosted on GitHub.

## What lives where

| Path | Contents |
|------|----------|
| `/home/agent` | The `agent` user: Claude Code, uv, mise and mait-code under `~/.local/bin`, all installed as the agent so each can update itself |
| `/home/agent/work` | Checkouts the agent works in. The only place it may edit without a prompt. Its group and mode are set by the [maitre_d role](../maitre_d/README.md#listing-the-agents-projects), which lets maitre-d list it |
| `/etc/claude-code/managed-settings.json` | Root-owned managed settings, templated from `claude_workstation_managed_settings` |
| `/etc/claude-code/CLAUDE.md` | The agent's identity as managed memory, installed from maitre-d's release by the [maitre_d role](../maitre_d/README.md#the-agents-identity) |
| `/usr/local/bin/fj`, `/usr/local/bin/yq` | Root-owned, pinned by version and checksum |
| `/etc/nftables.d/ingress.nft` | The inbound table; the outbound one is egress_proxy's |
| `/var/lib/maitre-d` | Home of the control service's account, and its data directory (see the [maitre_d role](../maitre_d/README.md)). `jobs/` and `snaps/` are where the session units read and write for it |
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
| `permissions.disableBypassPermissionsMode: disable` | Rejects `--dangerously-skip-permissions`, and a subagent's `bypassPermissions`. |
| `allowManagedHooksOnly: true` | The agent writes freely under `~/work`, and that includes each repository's `.claude/settings.json`. A hook declared there would run commands with no prompt in the next session. Only the hooks below run. |
| `allowManagedPermissionRulesOnly: true` | The same path, for allow rules: a repository could otherwise widen the agent's own permissions. A session's "always allow" is therefore not saved. Everything not on the allow list prompts. |

The **hooks** are an audit hook and mait-code's own three, which `mait-code install` writes into the user settings, where the lock above ignores them. They are copied with mait-code's timeouts and with `async` on the observe hooks, so compaction and session exit do not wait for them. Workflow jobs set `MAIT_CODE_NESTED=1`, mait-code's own recursion guard, so the observe hooks skip every stage. A stage is one fragment of a run, and an extractor on each would produce memories about half-finished work. So for now, jobs produce no memories. One extraction over the whole run, by maitre-d's runner, is planned to replace this. The audit hook sends every Bash command, with its session and working directory, to the journal before it runs:

```bash
journalctl -t claude-code-audit
```

The agent can also write to the journal under that tag, so treat the log as a record that cannot be erased, not as one that cannot be forged. When the pinned mait-code ref moves, compare `config/settings.json` at that ref with the three hooks declared in `defaults/main.yaml`.

The **allow list** is routine work that should not need a phone tap: reading and committing with git, `fj`, syncing and testing, mait-code's tools, read-only shell utilities, and WebSearch, which runs on Anthropic's side and so needs no name beyond the API. WebFetch is left to prompt: its fetches leave from this host, so any site it reads has to be on squid's list too, and each one added is a deliberate choice. It is convenience and visibility, **not containment**, and no list of patterns could make it containment:

- Several entries run code the agent can write. `uv run pytest` runs `conftest.py`, `git commit` runs `.git/hooks`, and `git fetch --upload-pack=<command>` runs a command outright.
- Several read files the deny rules below name. `git diff --no-index /dev/null ~/.git-credentials` prints the forge token without a prompt.
- `git push *` includes rewriting history (`+refspec`, `--mirror`, deletes). What stops that reaching `main` is branch protection on the forge, where only `matagoth` merges and nobody pushes.

So an injected session can run code and read the bot's credentials without asking. The managed settings stop it **persisting** a wider grant for later sessions (hooks, allow rules, connectors, bypass mode); they do not stop what a single session can do.

The agent is also denied running `claude` itself: `--safe-mode` would drop the managed `CLAUDE.md` that carries its identity, and no session here needs to start another. Like the read denials below, it stops the Bash tool, not a program the agent writes.

The **read denials** cover the forge token, SSH keys, Claude Code's own credentials and `.env` files. They stop the Read tool and plain shell reads such as `cat`. As above, they do not stop an allowed command or a program the agent writes, so they are a speed bump.

**Auto mode** is available, and is the default for a fresh interactive session. Prompts are not the boundary here (the allow list above already runs code), and a half-attended phone approval reviews less than auto mode's classifier, which reads every action. What auto mode waited for is the egress fence below, which contains where a session can reach: the LAN and any site off the allowlist. It does not contain what a session can read leaving through an allowlisted name that accepts uploads (GitHub, npm, Hugging Face, or the API itself under someone else's key); spotting that is left to the classifier. WebSearch results are another way injected text reaches a session without a prompt. Headless jobs run in auto mode too. With no one to answer a prompt, an action the classifier refuses ends in a denial, never a hang.

## Network posture

The host is fenced in both directions. The role depends on [egress_proxy](../egress_proxy/README.md), as the CI runners do, and adds an inbound table of its own.

**Enforcing.** `claude_workstation_egress_enforce` is `true`, with an allowlist built from what the workstation did in observation mode: Claude Code's API, login and updates, the uv, mise and npm toolchains and their registries, GitHub for mait-code and released binaries, and Hugging Face for mait-code's embedding model. A name off the list is refused, and the refusal shows as `TCP_DENIED` in squid's log. Widening it, and rebuilding the record for a new kind of work, are in the runbook ([post-deploy-setup](../../../docs/runbooks/post-deploy-setup.md#5-the-egress-fence)). With enforcement off, only PVE's own address is closed.

**Out.** Squid on `127.0.0.1:3128` is the agent's only way out, and it decides by name. The proxy variables are set in the managed settings' `env` (for Claude Code and every command a session runs) and at the top of the agent's `.bashrc` (for SSH shells). A program that ignores them is refused rather than let round the proxy. Beyond that:

- **The forge** is reached through squid as `forge.home.matagoth.com:3000`, Forgejo's own address and port, which the firewall opens to squid alone. This is the runners' path. It is never reached through nginx, because squid only sees the name in a `CONNECT`, while nginx picks a site by SNI and `Host`: a tunnel opened for the forge's name could then ask nginx for any site it fronts. The forge's public URL is rewritten by git, so a clone URL copied from the web UI works as it is.
- **The rest of the LAN** is closed, nginx included. PVE's address stays closed even with enforcement off.
- **NTP** leaves directly, from the timesync user only. A VM keeps its own clock, and the pool servers are names that resolve anywhere.
- **root and `_apt`** go out directly, so converges and apt keep working. The agent has neither.

Squid refuses ports other than 80 and 443 (and the forge's) even with enforcement off.

**In.** `table inet ingress` (`/etc/nftables.d/ingress.nft`, loaded by `ingress-firewall.service`) allows SSH only from the addresses in `claude_workstation_ssh_sources`: the laptop and the desktop for hands-on sessions, the apply-runner range for converges, and PVE so `run/host-key-push` works after a rebuild. ICMP is allowed; everything else inbound is refused. Refusals are recorded as for the egress table:

```bash
./run/host-ssh 218 'nft list set inet ingress observed_input'
```

**maitre-d's port** (`claude_workstation_service_port`, 8790) is open inbound to the reverse proxy alone, which lets only the laptop and the desktop through. The same table refuses the agent's own connections to it: a connection to the host's own address leaves through `lo`, which the egress table accepts, so the refusal is a reject of its own in an output chain. maitre-d's web UI only trusts the proxy as a peer, so the agent must never arrive from anywhere that looks like it.

**node_exporter** (`claude_workstation_metrics_port`, 9100) is open inbound to Prometheus (`claude_workstation_metrics_sources`) alone. The host lists the [node_exporter](../node_exporter/README.md) role in `config/vm/218.yaml`, with the systemd collector on and limited to the `claude-*` units and `maitre-d`. The agent can read the exporter over `lo`. Nothing is lost by that, because it could read the same counters from `/proc` and `systemctl` anyway. The *Workstation (218)* dashboard in Grafana reads from it, and it takes the VM's uptime from PVE's metric feed so that a stopped VM can be told apart from a dead exporter.

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
| `claude-job@<id>` | One run of maitre-d's workflow runner (`maitre-d-runner`) on one card, for maitre-d's scheduler. The runner is installed by the [maitre_d role](../maitre_d/README.md#the-workflow-runner). |
| `claude-snap@<project>` | A one-shot `tmux capture-pane` of the project's Remote Control pane. maitre-d reads the text, but never gets the tmux socket, which would also let it type into the session. |

**Remote Control** servers listed in `claude_workstation_rc_projects` start at boot. Any other checkout can be started on demand. `remote-control` exits cleanly when the login has expired, so every exit is restarted after a minute; five within fifteen minutes leave the unit **failed**, which is the state to alert on. Taking a project off the list does not disable its unit; `systemctl disable claude-rc@<project>` does. A changed unit template reaches a running server only when it is restarted.

**Every checkout under `~/work` is trusted.** Remote Control stops at `Trust this folder? [y/N]` the first time it runs anywhere, so `claude-trust` marks the unit's own checkout as trusted in `~/.claude.json` before each start. Running Claude Code processes rewrite that file without the script's lock, so a write racing the start can in principle drop the flag. The server then sits at the prompt with the unit **active**, which a snapshot shows. Trust lets a repository's project settings take effect. The managed settings already ignore its hooks and permission rules. What trust still allows is the rest of the project settings, such as helper commands and `.mcp.json` servers. Since the agent can write those files itself, the boundary is what reaches `~/work` in the first place: repositories granted to `matabot`.

**Jobs** read their configuration from `/var/lib/maitre-d/jobs/<id>/`, a directory only maitre-d can open:

| File | Written by | Contents |
|------|------------|----------|
| `job.env` | maitre-d | `CLAUDE_JOB_PROJECT=<checkout>` |
| `input.json` | maitre-d | The run input (workflow, card snapshot, what to do on a usage limit), sent on stdin |
| `result.json` | systemd, as root | The runner's outcome, from stdout |

systemd reads the environment file and opens both stdio files as root before it drops to the agent. So the agent can neither read nor change its input on disk, nor rewrite its result afterwards. The runner runs in the checkout `job.env` names, drives each stage of the workflow as one Agent SDK query in auto mode, and waits on each itself. A job is limited by `RuntimeMaxSec` (6 hours, the longest workflow's limit), `MemoryMax` and `CPUQuota`; stopping the unit sends the runner `SIGTERM`; once it has read its input it writes a `failed` outcome at once (before that, the result stays empty), and the whole cgroup goes. The outcome is agent-authored, since the runner runs as the agent, so maitre-d treats it as a claim, and any `denials` entry as needing attention. The outcome contract and the workflows are in maitre-d's `runner/README.md`.

**Snapshots** go to `/var/lib/maitre-d/snaps/<project>.txt`, written by systemd as root, so the agent cannot change a file once written. What goes into it is a different matter: the pane belongs to the agent, and any session can type into any project's tmux server, since they all run as the same user. Treat a snapshot as what the agent shows, not as evidence of what it did.

**maitre-d** may `start`, `stop`, `restart` and `reset-failed` units matching `claude-(rc|job|snap)@<name>.service`, and nothing else. `reset-failed` lets it clear a finished job once it has read the result, and recover a Remote Control server that hit its restart limit. It cannot enable or disable them, or touch any other unit. The polkit rule is the only thing it is delegated.

All three units run in `claude.slice`, which caps them together at 6G on top of each unit's 3G, and share one hardening block: `ProtectSystem=strict` with only the agent's home and the tmux directory writable, other homes hidden, a private `/tmp` and `/dev`, no capabilities and `NoNewPrivileges`. `systemd-analyze security` rates a job unit at 3.3 ("OK"). The role masks `tmp.mount`, so `/tmp` is on disk rather than trixie's default tmpfs, and the private `/tmp` with it. On tmpfs, whatever a session writes to `/tmp` is shmem charged to its unit's `MemoryMax`, and with no swap nothing can reclaim it: a job that cloned a handful of repositories into `/tmp` was OOM-killed that way. On disk it is page cache, which the kernel reclaims under pressure. Masking takes effect at the next boot; the converge says when one is due.

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
- **mait-code** follows `claude_workstation_mait_code_ref`: a converge re-runs the bootstrap whenever the agent's installed version differs, and `mait-code install` keeps files the agent has edited. Move it together with maitre-d's pin, since both open the same databases and refuse another schema version. When a release changes the memory schema or the embedding record, run the doctor once as the agent afterwards:

  ```bash
  ./run/host-ssh 218 'runuser -u agent -- env HOME=/home/agent /home/agent/.local/bin/mait-code doctor --fix'
  ```

  When the ref moves, also compare `config/settings.json` at the new ref with the hooks in `defaults/main.yaml` (see [Managed settings](#managed-settings)).
- **fj** and **yq**: bump the version and its `sha256` together. The checksum comes from the release artefact itself, so a version bump without a new checksum fails the download rather than installing something unverified.

## Rotating the forge token

Mint a new token and replace `MATABOT_FORGE_TOKEN` in `/pve/secrets/claude_workstation.sh` (see [post-deploy-setup](../../../docs/runbooks/post-deploy-setup.md#claude-code-workstation)). Then, on the host, remove fj's key store so the next converge writes the new token there too:

```bash
./run/host-ssh 218 'rm /home/agent/.local/share/forgejo-cli/keys.json'
```

Converge, then revoke the old token on the forge. `~/.git-credentials` is rewritten on every converge.
