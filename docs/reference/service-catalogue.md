# Service catalogue

Every name published under the `homelab.matagoth.com` zone is described by one entry in `config/services.yaml`. The file is the single source of truth for "what is reachable through the proxy" in the same way that a per-VMID file is the single source of truth for "what is this container".

Three consumers read it, and none of them keeps its own copy:

- **Terraform** creates one address record per entry, all pointing at the reverse proxy.
- **The reverse proxy role** renders one server block per entry, terminating TLS and forwarding to the entry's backend.
- **The index dashboard** renders one tile per entry, grouped by the categories the file declares.

Adding a service is therefore a single edit. This is a deliberate consequence of the lockstep principle: the failure mode the catalogue removes is the half-published service that resolves but does not proxy, or proxies but never appears on the index.

For the procedure, see [runbooks/add-service](../runbooks/add-service.md). For why the proxy is shaped the way it is, see [concepts/reverse-proxy](../concepts/reverse-proxy.md).

## Top-level shape

The file has two top-level keys. `categories:` declares the presentation hierarchy; `services:` declares the entries themselves. Both are ordered lists, and both orders are meaningful — they are the order the dashboard renders in.

Keeping the service list flat, rather than nesting entries inside their categories, is intentional. The proxy and the DNS records have no interest in presentation, and a flat list keeps those consumers reading a simple sequence while the dashboard does the grouping.

## Categories

A category has a name used for cross-referencing, a title used for display, a one-line description, and an ordered list of subcategories. A subcategory has just a name and a title.

The hierarchy is exactly two levels deep. This is enough to give the index a readable shape without the grouping becoming a taxonomy exercise, and it maps directly onto what the dashboard can render.

## Service entries

Each entry names a service and says where it lives:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | Identity. Becomes the DNS label, the proxy `server_name` prefix, and the dashboard link target |
| `title` | | Display name. Defaults to `name` |
| `category` | ✅ | Name of a declared category |
| `subcategory` | ✅ | Name of a subcategory declared within that category |
| `upstream` | ✅ | Backend URL the proxy forwards to, with scheme, port and trailing slash |
| `description` | ✅ | One line, shown beneath the title on the dashboard |
| `icon` | ✅ | Icon slug (see below) |
| `proxy` | | Set `false` to keep the entry out of DNS and the proxy. Defaults to true |
| `listed` | | Set `false` to keep the entry off the dashboard. Defaults to true |

The published address is derived from `name`, never written out. An entry that repeats its own URL in a second field is a bug waiting to drift; if you find yourself wanting one, the derivation is the thing to change.

`upstream` is the only place a backend address appears. It carries the scheme because backends disagree about TLS — several present self-signed certificates, which the proxy is configured not to verify.

## The two exception flags

`proxy: false` describes something worth listing on the index but not routing — a device with its own address that the proxy has no business fronting. `listed: false` describes the opposite: something routed but not worth a tile, of which the index itself is the obvious example, since a dashboard listing itself is noise.

Both default to true, so the common case declares neither.

## Icons

Icon slugs resolve against the dashboard's bundled icon set, with `mdi-` prefixed names falling back to Material Design Icons for services the set does not cover. A slug that does not resolve renders as a blank tile rather than failing the deploy, so a typo here is cosmetic and survives to production — worth checking against the icon set when adding an entry.

## Validation

`lint` checks the catalogue without needing infrastructure access: every service must reference a category and subcategory that exist, names must be unique, and the required fields must be present. Because the same file feeds three control planes, a typo that lint does not catch surfaces as a missing DNS record or a missing proxy block rather than as an obvious error, which is why the check runs on every change.

## Relationship to the internal zone

The catalogue governs the *public-facing* internal zone — the proxied `homelab.matagoth.com` names that a browser uses. It does not govern `home.matagoth.com`, the direct host-to-host zone, whose records point at real addresses and exist so containers can find each other without traversing the proxy. Those records remain declared individually in Terraform.

A service commonly appears in both: once as a direct address for machine-to-machine traffic, once through the proxy for browsers.
