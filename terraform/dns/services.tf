resource "dns_a_record_set" "ntfy" {
  zone      = "home.matagoth.com."
  name      = "ntfy"
  addresses = ["10.20.1.202"]
  ttl       = 500
}
