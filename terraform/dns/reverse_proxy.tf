locals {
  reverse_proxy_servers = [
    "www",
    "proxmox",
    "prometheus",
    "grafana",
    "opnsense",
    "uptime-kuma",
    "switch",
    "pihole",
    "portainer",
    "prowlarr",
    "jellyfin",
    "qbittorrent",
    "sabnzbd",
    "fileserver",
    "localai",
    "sonarr",
  ]
}

resource "dns_a_record_set" "rvp" {
  for_each = toset(local.reverse_proxy_servers)

  zone      = "homelab.matagoth.com."
  name      = each.key
  addresses = ["10.20.1.10"]
  ttl       = 500
}
