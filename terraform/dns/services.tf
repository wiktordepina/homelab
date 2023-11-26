resource "dns_a_record_set" "ntfy" {
  zone      = "home.matagoth.com."
  name      = "ntfy"
  addresses = ["10.20.1.202"]
  ttl       = 500
}

resource "dns_a_record_set" "jellyfin" {
  zone      = "home.matagoth.com."
  name      = "jellyfin"
  addresses = ["10.20.1.204"]
  ttl       = 500
}
