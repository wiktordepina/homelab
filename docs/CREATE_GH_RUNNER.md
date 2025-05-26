## Creating GitHub Actions runner

Create new LXC with id in range 500-599. Container requires extra mount points:
```
mp0: /zpool/secrets,mp=/pve/secrets
mp1: /zpool/terraform,mp=/pve/terraform
``` 


Run below in the container:

```shell
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
