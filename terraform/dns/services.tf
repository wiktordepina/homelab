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

resource "dns_a_record_set" "n8n" {
  zone      = "home.matagoth.com."
  name      = "n8n"
  addresses = ["10.20.1.211"]
  ttl       = 500
}

resource "dns_a_record_set" "homeassistant" {
  zone      = "home.matagoth.com."
  name      = "homeassistant"
  addresses = ["10.20.1.206"]
  ttl       = 500
}

resource "dns_a_record_set" "mosquitto" {
  zone      = "home.matagoth.com."
  name      = "mosquitto"
  addresses = ["10.20.1.212"]
  ttl       = 500
}

resource "dns_a_record_set" "netalertx" {
  zone      = "home.matagoth.com."
  name      = "netalertx"
  addresses = ["10.20.1.213"]
  ttl       = 500
}

resource "dns_a_record_set" "netbox" {
  zone      = "home.matagoth.com."
  name      = "netbox"
  addresses = ["10.20.1.215"]
  ttl       = 500
}

resource "dns_a_record_set" "mait" {
  zone      = "home.matagoth.com."
  name      = "mait"
  addresses = ["10.20.30.40"]
  ttl       = 500
}

resource "dns_a_record_set" "forge" {
  zone      = "home.matagoth.com."
  name      = "forge"
  addresses = ["10.20.1.216"]
  ttl       = 500
}

resource "dns_a_record_set" "hermes" {
  zone      = "home.matagoth.com."
  name      = "hermes"
  addresses = ["10.20.1.217"]
  ttl       = 500
}
