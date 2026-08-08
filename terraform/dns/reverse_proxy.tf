locals {
  # The service catalogue is shared with Ansible, which renders the matching
  # nginx server blocks from the same entries. See config/services.yaml.
  service_catalogue = yamldecode(file("${path.module}/../../config/services.yaml"))

  reverse_proxy_servers = [
    for service in local.service_catalogue.services :
    service.name if try(service.proxy, true)
  ]
}

resource "dns_a_record_set" "rvp" {
  for_each = toset(local.reverse_proxy_servers)

  zone      = "homelab.matagoth.com."
  name      = each.key
  addresses = ["10.20.1.10"]
  ttl       = 500
}
