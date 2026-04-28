# Reverse proxy

The reverse proxy is the LAN-side front door for services with a browser UI. It terminates TLS using a wildcard certificate and forwards to the appropriate backend. This document covers what the proxy is responsible for, the recurring footguns, and the boundaries of its role.

## What the proxy is for

The proxy answers a single question: how do you reach a homelab service from a browser, on the LAN, without certificate warnings and without typing IP addresses or port numbers?

Every backend service it fronts already speaks HTTP (or HTTPS) on its container's address. The proxy adds three things on top: a friendly hostname under `homelab.matagoth.com`, valid TLS, and a single point of TLS-cert renewal. Everything else — authentication, routing logic, rate limiting — is the backend's responsibility. The codeowner deliberately keeps the proxy thin.

The proxy is **not** an internet front door. It is not exposed beyond the LAN. Public exposure goes through an entirely different path; see [domains-and-tls](domains-and-tls.md).

## Why TLS terminates at the proxy and not at each backend

Each homelab service could in principle run its own TLS. The proxy exists so that there is exactly one certificate (a wildcard for `*.homelab.matagoth.com`) to renew on exactly one container, rather than N certificates on N services with N different renewal mechanisms. The operational cost of running TLS is paid once, and every service behind the proxy benefits.

A consequence is that the path between the proxy and the backend is plain HTTP. The codeowner accepts this because the path is on the LAN, between containers on the same host. If the threat model ever requires container-to-container encryption, the model has to change; today it does not.

## The WebSocket-class footgun

A recurring problem with naive reverse-proxy configuration is that **services with live state do not work**. You deploy the service, the page loads, and then nothing updates — clicks have no effect, dashboards stay frozen, new events never appear. The cause is almost always the same: the proxy is stripping the headers and protocol upgrade that real-time browsers need.

Several services in the homelab depend on WebSockets or long-lived streaming connections for their normal operation. Their UIs *appear* to work over a basic HTTP/1.0 proxy and only break for the live-update path. The breakage is silent: there is no error, just a UI that does not move.

The proxy's configuration in the `nginx_reverse_proxy` Ansible role is therefore expected to support, by default, every backend that needs WebSockets — not as a per-service opt-in. The codeowner's pattern is "configure the proxy correctly once, treat it as table-stakes, never tune it per-service unless there is a strong reason". Specifically the proxy advertises HTTP/1.1 to backends, forwards the upgrade and connection headers, and passes the original scheme so backends can build correct URLs.

This is a *concept* to hold rather than a config to copy: when a new service appears to half-work, suspect the proxy configuration before suspecting the service.

## Trusted proxies on the backend

Some backends — notably ones that build absolute URLs or enforce origin checks — need to know that they are sitting behind a proxy. They expose this as a "trusted proxies" or "forwarded headers" setting. The setting names the proxy's address and tells the backend to honour the forwarded-host and forwarded-proto headers it sends.

If this is missing, the backend either rejects requests outright (origin mismatch) or generates URLs with the wrong scheme or hostname (often `http://` or the container's IP) and breaks redirects, asset URLs, and OAuth callbacks. The fix is on the backend, not on the proxy.

When wiring up a new browser-facing service, the question to ask is "does this service know it is behind a reverse proxy?" — and to answer it before declaring the service done.

## What the proxy does not do

The proxy does not authenticate users; backends authenticate their own users. The proxy does not rewrite payloads; it forwards them as-is. The proxy does not load-balance; there is one backend per route. The proxy does not handle public exposure; that is Cloudflare Tunnel's job. The codeowner keeps the proxy thin precisely because that makes it cheap to reason about and rare to need to change.

## Adding a backend

Adding a new backend to the proxy is part of the service-lifecycle checklist; see [service-lifecycle](service-lifecycle.md) and the [add-service runbook](../runbooks/add-service.md). It involves two coordinated edits: the proxy configuration learns about the new backend, and the LAN-side proxy DNS zone gains a record pointing the friendly name at the proxy. Either edit alone produces a non-working state.
