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

resource "dns_a_record_set" "localai" {
  zone      = "home.matagoth.com."
  name      = "localai"
  addresses = ["10.20.1.207"]
  ttl       = 500
}

 resource "dns_a_record_set" "prometheus" {
  zone      = "home.matagoth.com."
  name      = "prometheus"
  addresses = ["10.20.1.210"]
  ttl       = 500
}
