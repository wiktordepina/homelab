# egress_proxy

Confines a host's outbound traffic to a list of names. It puts squid on the host as a forward proxy that allows or refuses each request by host name, and loads an nftables table that makes the proxy the only way out. It is written for hosts that run code nobody reviewed line by line: CI runners now, and agent sandboxes later.

nftables cannot allowlist by host name. The services a job legitimately needs (GitHub releases, PyPI, npm, Docker Hub) sit on CDNs whose addresses move and are shared with everything else on the same CDN, so an address allowlist is either wrong within a week or wide open. Squid sees the name a client asks for, in the `CONNECT` line or the request URL, and decides on that.

## What it puts on the host

| Piece | Where | What it does |
|------|------|------|
| squid | `/etc/squid/squid.conf`, `/etc/squid/allowlist.txt` | Listens on `egress_proxy_port` (3128). Allows a name in the allowlist, refuses anything else. No caching, and no TLS interception: a tunnel is allowed or refused on its host name, and what passes inside it is not inspected. |
| nftables | `table inet egress`, from `/etc/nftables.d/egress.nft` | The fence. See below. |
| `egress-firewall.service` | systemd | Loads that one table at boot, before the network and Docker. `systemctl reload egress-firewall` re-applies it; `stop` removes it. |

The table is replaced atomically and on its own. The role never uses `/etc/nftables.conf` or `nftables.service`: Debian's default file begins with `flush ruleset`, and on a Docker host a reload of it would wipe Docker's iptables-nft tables along with everything else.

## The fence

- **Client interfaces** (`egress_proxy_client_interfaces`, Docker's bridges on a runner) are for traffic that is not the host's own. Their packets may reach squid and the ports in `egress_proxy_client_ports` on this host, and nothing else. Anything they try to forward is dropped, DNS included, so name resolution goes through the proxy and DNS cannot be used as a tunnel.
- **The host itself** may reach the resolver, the destinations in `egress_proxy_direct_destinations`, and its own client interfaces. A destination marked `squid_only` is open to squid alone, so the host reaches it by an allowlisted name and never by address. That is how one name on the reverse proxy is allowed without every other site it fronts. With `egress_proxy_ntp_user` set, that user's NTP queries may leave for any address; a VM needs this, a container takes its clock from the host. Ports 80 and 443 to the internet are open only to squid's user and to `egress_proxy_direct_users`, which are root and `_apt` by default. Fencing root would buy nothing, because a root process in the container can rewrite the table. Fencing `_apt` would break every converge, because apt fetches as `_apt`. The rest of the LAN is closed.
- **`egress_proxy_blocked_destinations`** (the PVE management address) can never be connected to, observation mode included. Replies are still let through, so the address can connect in: PVE pushing an SSH key with `run/host-key-push` keeps working.
- **Squid's own ports** are reachable only from loopback and the client interfaces, so the proxy is never an open relay on the LAN.

## Observation, then enforcement

`egress_proxy_enforce: false` runs everything with the fence's verdicts set to accept and squid allowing every name, while both keep a record of what they would have refused:

```bash
# Every name asked for, with squid's verdict, most frequent first
./run/host-ssh <vmid> 'awk "{print \$4, \$6, \$7}" /var/log/squid/access.log \
  | sed -E "s#(https?://[^/]+).*#\1#" | sort | uniq -c | sort -rn'

# Traffic that tried to go round the proxy (client interfaces) or out from the host
./run/host-ssh <vmid> 'nft list set inet egress observed_forward; nft list set inet egress observed_output'

# Rule counters
./run/host-ssh <vmid> 'nft list table inet egress | grep "counter packets [1-9]"'
```

nftables `log` statements produce nothing inside a container's network namespace, which is why the record is kept in sets rather than in a log. The sets hold IPv4 addresses, with protocol and port, for seven days.

A host starts in observation mode and its allowlist is built from that record, not from anyone's guess. Once the workload has run cleanly through the proxy, set enforcement on. The same commands then show what is being refused.

## Accepted residuals

This raises the bar; it does not seal anything.

- **Allowed names can carry data out.** An allowlisted destination that accepts uploads with credentials of the uploader's choosing is still an exfiltration route. `github.com` is the plainest example: allowed because toolchains are released there, and also able to receive a push to someone else's repository.
- **Names are matched, contents are not.** With no TLS interception, a client that `CONNECT`s to an allowed name can send a different TLS server name inside the tunnel. Behind a CDN that routes by that name (domain fronting), this reaches other sites on the same CDN.
- **Root is not contained.** Anything running as root on the host can change the table. The fence contains the workload (job containers, unprivileged users), not a compromised host.
