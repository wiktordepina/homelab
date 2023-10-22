terraform {
  backend "local" {}
  required_providers {
    dns = {
      source  = "hashicorp/dns"
      version = "3.3.2"
    }
  }
}

provider "dns" {
  update {
    server        = var.dns_ip
    key_name      = "tsig-key."
    key_algorithm = "hmac-sha256"
    key_secret    = var.tsig_key
  }
}
