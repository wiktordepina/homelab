resource "dns_a_record_set" "www" {
  zone      = "homelab.matagoth.com."
  name      = "www"
  addresses = ["10.20.1.10"]
  ttl       = 500
}
