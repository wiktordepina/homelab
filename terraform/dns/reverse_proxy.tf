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
