terraform {
  backend "local" {}
  required_providers {
    proxmox = {
      source  = "terraform.local/telmate/proxmox"
      version = "1.0.0"
    }
  }
}

provider "proxmox" {
  pm_api_url      = "https://192.168.200.100:8006/api2/json"
  pm_tls_insecure = true
}
