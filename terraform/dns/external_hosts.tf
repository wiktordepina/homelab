resource "dns_a_record_set" "pi_01" {
  zone      = "home.matagoth.com."
  name      = "pi-01"
  addresses = ["10.10.50.10"]
  ttl       = 500
}
