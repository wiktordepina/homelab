# ariel

Deploys ariel, the workstation agents' way to read the web, on its own LXC. ariel is an MCP server with `search(query)` and `fetch(id, question)`: search results and page links come back as opaque ids, never URLs, and a page is read by a quarantine model that answers the agent's question in a capped schema, so the raw page never reaches the agent. What ariel does, its configuration and its threat model are in its own repository (`matagoth-zaibatsu/ariel`, `docs/spike.md`); this README covers how it is deployed.

## The host's fences

ariel parses hostile pages, so its host holds nothing worth stealing and reaches nothing worth attacking.

- **Out:** `egress_proxy` (a dependency of this role) in enforcing, open-web mode. squid reaches any public address and refuses private ones, with one exception by name: LiteLLM, for the quarantine calls, on its own address and port (`localai.home.matagoth.com:4000`), which the firewall opens to squid alone. Never through the reverse proxy: squid only sees the name in a `CONNECT`, while nginx picks a site by SNI and `Host`, so a tunnel opened for LiteLLM's public name could ask nginx for any site it fronts, PVE's UI included. Plain HTTP inside the DMZ, as the forge is reached from the runners; squid forwards it by URL, so there is no tunnel to switch sites in. The containers are Docker clients: the only thing on the host they can reach is squid, and nothing they send is forwarded beyond it. ariel sends every page fetch and LiteLLM call through squid, and SearXNG sends every search, so squid resolves every name the containers use.
- **In:** a table of the role's own, `inet ingress`. Docker's published ports are DNATed and pass the *forward* hook, not input, so the table has both chains. The MCP port (8792) is open to the workstation alone, the metrics port (9102) and node_exporter (9100) to Prometheus alone, and SSH to the usual sources. Everything else is dropped, and the drops are recorded by source in the `observed_input` set. The admin port of the registered-URLs API is not open yet: that is ariel's next release.
- **Secrets:** two capped keys. The LiteLLM key, restricted to one model (`ariel-quarantine`) and the LLM routes, with a monthly hard budget; and the Brave Search API key, with a spending limit on Brave's dashboard. Nothing else: the forge token stays on the apply runner.

## Installing a release

`ariel_version` and `ariel_commit` pin a release tag on the forge. When the commit recorded in `/opt/ariel/src/.commit` differs, the converge clones the tag **on the apply runner**, with `forge-deploy`'s read-only token from `/pve/secrets/ariel.sh`. It fails unless the clone is the pinned commit, then ships the tree to 219 as a `git archive`. 219 never reaches the forge and never holds a token that can read private repositories.

The image is built on 219, from the shipped tree, when no `ariel:<version>` image carries the pinned commit in its revision label. The build's RUN steps go through squid for PyPI. Docker pulls the base images directly as root.

The release's `deploy/searxng/settings.yml` is used as shipped, with two additions: `outgoing.proxies` points SearXNG at squid, and the `braveapi` engine gets its `api_key`. SearXNG has no environment expansion for engine keys, so the key is written into the file, which is why it is readable by root and SearXNG's group alone. The converge fails if the release has no `braveapi` engine, rather than leaving the key unwritten.

To move to a new release, bump `ariel_version` and `ariel_commit` and converge. The converge waits for `/healthz` to report the new version.

## What lives where

| Path | Owner, mode | Contents |
|------|-------------|----------|
| `/opt/ariel/src` | root | The pinned release's tree, and `.commit` |
| `/opt/ariel/compose.yaml` | root `0644` | ariel and SearXNG, both on read-only roots with no capabilities, as non-root users |
| `/opt/ariel/ariel.toml` | root `0644` | ariel's configuration: only what differs from its defaults |
| `/opt/ariel/searxng/settings.yml` | root:977 `0640` | The release's SearXNG settings plus the proxy and the Brave key |
| `/opt/ariel/.env` | root `0600` | `ARIEL_LITELLM_KEY` and `SEARXNG_SECRET`, for compose |
| Docker volume `ariel_ariel-data` | ariel's uid | `ariel.db`: ids, budgets and the page cache |
| `/etc/nftables.d/ingress.nft` | root | The inbound table, loaded by `ingress-firewall.service` before Docker |

## Logs

ariel logs one line per call to stdout, with the result, the domain and the cost; queries appear only as a hash and a length. They stay on the host:

```bash
./run/host-ssh 219 'docker compose -f /opt/ariel/compose.yaml logs --since 24h ariel'
```

This is where to look after a cap hit on the dashboard: the metrics deliberately carry no domains.

## When an engine goes quiet

SearXNG reports a failing engine, and one with a missing or rejected key, only as an engine that returned nothing (`silent`) or that it listed as failed (`unresponsive`); the search itself still succeeds on the other engines. `ariel_search_engines_total` counts each engine's outcome per search, and the *Search engines* panel on the `ariel (219)` dashboard shows it. `braveapi` with no `answered` while searches go on means the key is wrong, revoked, or past its spending limit on Brave's dashboard.

## Secrets

`/pve/secrets/ariel.sh` on the apply runner exports `ARIEL_FORGE_TOKEN`, `ARIEL_LITELLM_KEY`, `ARIEL_SEARXNG_SECRET` and `ARIEL_BRAVE_API_KEY`. How each is made, and how the Brave key is rotated, is in the [post-deploy-setup runbook](../../../docs/runbooks/post-deploy-setup.md#ariel).
