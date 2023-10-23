resource "dns_a_record_set" "router" {
  zone = "matagoth.com."
  name = "router"
  addresses = [
    "10.10.0.1",
    "10.20.0.1",
    "10.50.0.1",
    "192.168.200.1"
  ]
  ttl = 500
}

resource "dns_a_record_set" "switch" {
  zone      = "matagoth.com."
  name      = "switch"
  addresses = ["192.168.200.50"]
  ttl       = 500
}

resource "dns_a_record_set" "accesspoint" {
  zone      = "matagoth.com."
  name      = "accesspoint"
  addresses = ["192.168.200.60"]
  ttl       = 500
}
