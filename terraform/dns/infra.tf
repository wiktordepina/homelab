resource "dns_a_record_set" "router" {
  zone = "home.matagoth.com."
  name = "router"
  addresses = [
    "10.10.0.1",
    "10.20.0.1",
    "10.50.0.1",
    "10.100.0.1",
    "192.168.200.1"
  ]
  ttl = 500
}

resource "dns_a_record_set" "reverse_proxy" {
  zone      = "home.matagoth.com."
  name      = "www"
  addresses = ["10.20.1.10"]
  ttl       = 500
}

resource "dns_a_record_set" "switch" {
  zone      = "home.matagoth.com."
  name      = "switch"
  addresses = ["192.168.200.50"]
  ttl       = 500
}

resource "dns_a_record_set" "accesspoint" {
  zone      = "home.matagoth.com."
  name      = "accesspoint"
  addresses = ["192.168.200.60"]
  ttl       = 500
}

resource "dns_a_record_set" "proxmox" {
  zone      = "home.matagoth.com."
  name      = "proxmox"
  addresses = ["192.168.200.100"]
  ttl       = 500
}

resource "dns_a_record_set" "pihole" {
  zone      = "home.matagoth.com."
  name      = "pihole"
  addresses = ["10.20.1.1"]
  ttl       = 500
}

resource "dns_a_record_set" "fileserver" {
  zone      = "home.matagoth.com."
  name      = "fileserver"
  addresses = ["10.20.1.203"]
  ttl       = 500
}

resource "dns_a_record_set" "dockerhost" {
  zone      = "home.matagoth.com."
  name      = "dockerhost"
  addresses = ["10.20.1.205"]
  ttl       = 500
}
