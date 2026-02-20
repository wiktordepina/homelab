# Creating GitHub Actions Runner

> **Navigation:** [← Back to README](../README.md) | [Runner Toolbox](RUNNER_TOOLBOX.md)

## Overview

GitHub Actions runners are self-hosted in LXC containers (ID range 500-599) to execute CI/CD workflows. The runner executes the [runner-toolbox](RUNNER_TOOLBOX.md) Docker container for Terraform and Ansible operations.

## Prerequisites

- Proxmox VE access
- GitHub repository admin access (to generate runner token)
- Mount points available on host

## Create the LXC Container

Create new LXC with ID in range 500-599. Container requires extra mount points:

```
mp0: /zpool/secrets,mp=/pve/secrets
mp1: /zpool/terraform,mp=/pve/terraform
```

## Install the Runner

Run the following in the container:

```bash
# => setup env
GH_RUNNER_VERSION=2.322.0
read -p 'Input GitHub Actions Runner Token: ' GH_RUNNER_TOKEN

# => create a folder
mkdir actions-runner && cd actions-runner

# => download the latest runner package
curl -O -L "https://github.com/actions/runner/releases/download/v${GH_RUNNER_VERSION}/actions-runner-linux-x64-${GH_RUNNER_VERSION}.tar.gz"

# => extract the installer
tar xzf ./actions-runner-linux-x64-${GH_RUNNER_VERSION}.tar.gz
./bin/installdependencies.sh

# => config and install service
RUNNER_ALLOW_RUNASROOT=1 ./config.sh --url https://github.com/wiktordepina/homelab --token "${GH_RUNNER_TOKEN}"
./svc.sh install root
./svc.sh start
```

## Build the Runner Toolbox

After the runner is configured, build the toolbox Docker image:

```bash
cd /build
git clone https://github.com/wiktordepina/homelab.git
cd homelab/runner-toolbox
docker build -t runner-toolbox .
```

## Verify Installation

1. Check runner appears in GitHub: Repository → Settings → Actions → Runners
2. Test the toolbox: `./run/execute_runner --version`

## Getting the Runner Token

1. Go to your GitHub repository
2. Navigate to: Settings → Actions → Runners
3. Click "New self-hosted runner"
4. Copy the token from the configuration command

The token expires after a short time, so use it immediately.

## Updating the Runner

To update to a new version:

```bash
cd ~/actions-runner
./svc.sh stop

# Update version and re-download
GH_RUNNER_VERSION=2.323.0  # New version
curl -O -L "https://github.com/actions/runner/releases/download/v${GH_RUNNER_VERSION}/actions-runner-linux-x64-${GH_RUNNER_VERSION}.tar.gz"
tar xzf ./actions-runner-linux-x64-${GH_RUNNER_VERSION}.tar.gz

./svc.sh start
```

## Troubleshooting

### Runner Not Appearing in GitHub

- Verify the token hasn't expired
- Check network connectivity to GitHub
- Review logs: `journalctl -u actions.runner*`

### Runner Can't Access Secrets

Ensure mount points are correct:
```bash
ls -la /pve/secrets/
ls -la /pve/terraform/
```

## Related Documentation

- [Runner Toolbox](RUNNER_TOOLBOX.md) - CI/CD automation tooling
- [Workflows](WORKFLOWS.md) - How to use the runner
