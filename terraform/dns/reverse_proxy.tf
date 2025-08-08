resource "dns_a_record_set" "www" {
  zone      = "homelab.matagoth.com."
  name      = "www"
  addresses = ["10.20.1.10"]
  ttl       = 500
}

resource "dns_a_record_set" "rvp_proxmox" {
  zone      = "homelab.matagoth.com."
  name      = "proxmox"
  addresses = ["10.20.1.10"]
  ttl       = 500
}

resource "dns_a_record_set" "rvp_prometheus" {
  zone      = "homelab.matagoth.com."
  name      = "prometheus"
  addresses = ["10.20.1.10"]
  ttl       = 500
}

resource "dns_a_record_set" "rvp_grafana" {
  zone      = "homelab.matagoth.com."
  name      = "grafana"
  addresses = ["10.20.1.10"]
  ttl       = 500
}

resource "dns_a_record_set" "rvp_opnsense" {
  zone      = "homelab.matagoth.com."
  name      = "opnsense"
  addresses = ["10.20.1.10"]
  ttl       = 500
}

resource "dns_a_record_set" "rvp_uptime_kuma" {
  zone      = "homelab.matagoth.com."
  name      = "uptime-kuma"
  addresses = ["10.20.1.10"]
  ttl       = 500
}

resource "dns_a_record_set" "rvp_switch" {
  zone      = "homelab.matagoth.com."
  name      = "switch"
  addresses = ["192.168.200.50"]
  ttl       = 500
}

resource "dns_a_record_set" "rvp_pihole" {
  zone      = "homelab.matagoth.com."
  name      = "pihole"
  addresses = ["192.168.200.50"]
  ttl       = 500
}

resource "dns_a_record_set" "rvp_portainer" {
  zone      = "homelab.matagoth.com."
  name      = "portainer"
  addresses = ["192.168.200.50"]
  ttl       = 500
}

resource "dns_a_record_set" "rvp_prowlarr" {
  zone      = "homelab.matagoth.com."
  name      = "prowlarr"
  addresses = ["192.168.200.50"]
  ttl       = 500
}

resource "dns_a_record_set" "rvp_jellyfin" {
  zone      = "homelab.matagoth.com."
  name      = "jellyfin"
  addresses = ["192.168.200.50"]
  ttl       = 500
}
