variable "vmid" {
  type    = number
  default = 0
}

variable "hostname" {
  type = string
}

variable "ip_address" {
  type = string
}

variable "nameserver" {
  type    = string
  default = "10.20.0.1"
}

variable "gateway" {
  type    = string
  default = "10.20.0.1"
}

variable "cpu_core_count" {
  type    = number
  default = 1
}

variable "cpu_socket_count" {
  type    = number
  default = 1
}

variable "memory" {
  type    = number
  default = 1024
}

variable "rootfs_size" {
  type    = string
  default = "8G"
}

variable "network_bridge" {
  type    = string
  default = "vmbr1"
}

variable "storage" {
  type    = string
  default = "local-zpool"
}

variable "template" {
  type    = string
  default = "tmpl-debian-13-cloudinit"
}

variable "start_on_boot" {
  type    = bool
  default = false
}

variable "ssh_public_keys" {
  type    = string
  default = ""
}

variable "usb_passthrough" {
  type = list(object({
    host = string
  }))
  default = []

  validation {
    condition     = length(var.usb_passthrough) <= 1
    error_message = "The VM module currently exposes only one USB slot (usb0). Extend main.tf with usb1..usb4 dynamic blocks before increasing this limit."
  }
}

variable "extra_networks" {
  type = list(object({
    bridge = string
    tag    = optional(number)
  }))
  default = []
}
