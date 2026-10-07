# claude_workstation

Turns a VM into a host where Claude Code works unattended or from the phone, as an unprivileged user, under settings it cannot change. It works on forge repositories granted to the `matabot` account and on nothing hosted on GitHub.

## What lives where

| Path | Contents |
|------|----------|
| `/home/agent` | The `agent` user: Claude Code, uv, mise and mait-code under `~/.local/bin`, all installed as the agent so each can update itself |
| `/home/agent/work` | Checkouts the agent works in. The only place it may edit without a prompt |
| `/etc/claude-code/managed-settings.json` | Root-owned managed settings, templated from `claude_workstation_managed_settings` |
| `/usr/local/bin/fj`, `/usr/local/bin/yq` | Root-owned, pinned by version and checksum |
| `/var/lib/maitre-d` | Home of the control service's account, which is created here but not yet used |

## The agent

`agent` has no sudo and no privileged group. The managed settings only bind because the agent cannot write `/etc`, so anything that gave it root, including membership of `docker`, would undo all of them. If containers are ever needed, they run rootless as the agent.

It reaches the forge over HTTPS as `matabot`, with one token in `~/.git-credentials` (for git) and in fj's own key store. HTTPS rather than SSH means one credential and one revocation. There is no GitHub credential on the host at all.

`~/.ssh/id_ed25519` is generated for reading other guests through a restricted observer account. Nothing distributes it yet.

## Managed settings

| Setting | Why |
|---------|-----|
| `disableClaudeAiConnectors: true` | The subscription login brings the account's claude.ai connectors (Gmail, Drive, Calendar) into the agent, already connected. A session that has been steered by injected text could then read and send mail as the account holder, through endpoints any egress allowlist has to permit. A user-settings override does not bring them back. |
| `disableAutoMode: disable` | Sessions here are often half-attended from a phone. Auto mode is where Claude Code's own judgement replaces the human's. |
| `permissions.disableBypassPermissionsMode: disable` | Rejects `--dangerously-skip-permissions`, and a subagent's `bypassPermissions`. |
| `allowManagedHooksOnly: true` | The agent writes freely under `~/work`, and that includes each repository's `.claude/settings.json`. A hook declared there would run commands with no prompt in the next session. Only the hooks below run. |
| `allowManagedPermissionRulesOnly: true` | The same path, for allow rules: a repository could otherwise widen the agent's own permissions. A session's "always allow" is therefore not saved. Everything not on the allow list prompts. |

The **hooks** are an audit hook and mait-code's own three, which `mait-code install` writes into the user settings, where the lock above ignores them. The audit hook sends every Bash command, with its session and working directory, to the journal before it runs:

```bash
journalctl -t claude-code-audit
```

The agent can also write to the journal under that tag, so treat the log as a record that cannot be erased, not as one that cannot be forged. When the pinned mait-code ref moves, compare its hooks with the three declared in `defaults/main.yaml`.

The **allow list** is routine work that should not need a phone tap: reading and committing with git, `fj`, syncing and testing, mait-code's tools and read-only shell utilities. Allowing something that runs project code is allowing code execution, because the agent writes that code. `uv run pytest` runs `conftest.py`, and `git commit` runs `.git/hooks`. The second is closed by denying the Edit tool inside `.git/` in work repositories; the first is accepted. **The prompt is not the security boundary.** The VM and the credentials the host does not hold are. Force-pushes always ask.

The **read denials** cover the forge token, SSH keys, Claude Code's own credentials and `.env` files. They stop the Read tool and shell file commands such as `cat`. They do not stop a program the agent writes from opening the file, so they are a speed bump, not a wall.

The Bash sandbox is not used, so `bubblewrap` and `socat` are not installed.

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
