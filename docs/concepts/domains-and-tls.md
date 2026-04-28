# Domains and TLS

The homelab uses three distinct zones, each with a different purpose, a different TLS story, and a different IaC story. Conflating them is the source of most "why does this not resolve" or "why is the certificate wrong" confusion.

## The three zones

**Internal discovery zone.** Container hostnames live here. Names resolve directly to container IP addresses, with no proxy in between. This zone exists so that one container can find another by name, and so that operators on the LAN can reach services without going through any kind of front door. There is no TLS on this path; it is plain HTTP (or whatever the service speaks natively). The zone is fully managed in this repository.

**LAN-side reverse-proxy zone.** Names in this zone all resolve to one address: the reverse proxy. The proxy terminates TLS using a wildcard certificate and forwards to the appropriate backend. This zone exists for the operator's browser: it is the convenient, encrypted, named way to reach services on the LAN. It is not exposed to the internet, and it is not the canonical name a service uses to find another service. The zone is fully managed in this repository.

**Public zone.** A small number of services are intentionally exposed to the internet. Public access goes through a Cloudflare Tunnel running in a dedicated container; the tunnel terminates TLS at Cloudflare's edge using Cloudflare-managed certificates. The public zone routes are configured manually in the Cloudflare dashboard today. This is the one significant carve-out from "everything is IaC" — see below.

## Where TLS terminates

| Path | Terminator | Certificate |
|---|---|---|
| Internal discovery | None — plain | None |
| LAN-side proxy | Reverse-proxy container on the LAN | Wildcard, renewed via DNS-01 |
| Public | Cloudflare's edge | Cloudflare-managed |

The wildcard certificate for the LAN-side zone is renewed by an ACME client running in the reverse-proxy container, using DNS-01 with the domain registrar. Renewal is automatic; rotation as a manual procedure is covered in [runbooks/rotate-wildcard-cert](../runbooks/rotate-wildcard-cert.md).

## What is and is not in IaC

Everything about the internal discovery zone and the LAN-side proxy zone — record sets, proxy configuration, certificate renewal — is in this repository and applied through the runner.

The public zone's *DNS records* are managed at the registrar and proxied via Cloudflare. Cloudflare's *route table* — which hostname maps to which tunnel-internal target — is configured by hand in the Cloudflare dashboard. Today only one public route exists, so this has not been painful, but it is acknowledged technical debt and a candidate for future IaC. If the set of public routes grows, that work becomes more pressing.

The tunnel *credential* (the long-lived token the tunnel uses to register itself with Cloudflare) is in the homelab's secrets store and consumed by the tunnel container at startup. The credential is in IaC; the routing decisions on top of it are not.

## Choosing a zone for a new service

A new service almost always needs an entry in the internal discovery zone. That is the one path that other containers will use to talk to it, and it costs nothing.

If the service has a UI that the operator will reach from a browser on the LAN, it usually also needs an entry in the LAN-side proxy zone. The exception is services where TLS is unwanted (some legacy admin UIs) or services that already terminate TLS themselves and would conflict with the proxy.

Public exposure is opt-in and rare. A service should only appear in the public zone if there is a concrete reason for it to be reachable from the internet. The default is no.

## Why three zones rather than one

The zones exist because they answer three different questions: *how do containers find each other*, *how does the operator's browser reach a service securely on the LAN*, and *how does the internet reach the few services we choose to expose*. Collapsing them — for example, putting all internal traffic through the LAN proxy — would couple unrelated paths and create a single point of failure where none needs to exist. The current split is verbose at setup time, but each path stays independent thereafter.
