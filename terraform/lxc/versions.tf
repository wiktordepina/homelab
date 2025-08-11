terraform {
  backend "local" {}
  required_providers {
    proxmox = {
      # source  = "Telmate/proxmox"
      # version = "3.0.2-rc03"
      source = "terraform.local/telmate/proxmox"
      version = "1.0.0"
    }
  }
}

provider "proxmox" {
  pm_api_url = "https://192.168.200.100:8006/api2/json"
  
  pm_tls_insecure = true

  #   pm_log_enable = true
  #   pm_log_file = "terraform-plugin-proxmox.log"
  #   pm_debug = true
  #   pm_log_levels = {
  #     _default = "debug"
  #     _capturelog = ""
  #  }
}
