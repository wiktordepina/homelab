terraform {
  backend "local" {}
  required_providers {
    proxmox = {
      source  = "Telmate/proxmox"
      version = "2.9.14"
    }
  }
}

provider "proxmox" {
  pm_api_url = "https://pve.matagoth.com:8006/api2/json"

  #   pm_log_enable = true
  #   pm_log_file = "terraform-plugin-proxmox.log"
  #   pm_debug = true
  #   pm_log_levels = {
  #     _default = "debug"
  #     _capturelog = ""
  #  }
}
