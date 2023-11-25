variable "hostname" {
  type = string
}

variable "ip_address" {
  type = string
}

variable "root_password" {
  type      = string
  sensitive = true
}

variable "cpu_core_count" {
  type    = number
  default = 4
}

variable "network_bridge" {
  type    = string
  default = "vmbr3"
}

variable "memory" {
  type    = number
  default = 2048
}

variable "swap" {
  type    = number
  default = 512
}

variable "nameserver" {
  type    = string
  default = "10.20.0.1"
}

variable "gateway" {
  type    = string
  default = "10.20.0.1"
}

variable "start_on_boot" {
  type    = bool
  default = false
}

variable "storage" {
  type    = string
  default = "local-zpool"
}

variable "rootfs_size" {
  type    = string
  default = "20G"
}

variable "enable_keyctl" {
  type    = bool
  default = true
}

variable "enable_nesting" {
  type    = bool
  default = true
}

variable "ssh_public_keys" {
  type    = string
  default = ""
}

variable "start_after_creation" {
  type    = bool
  default = false
}

variable "unprivileged" {
  type    = bool
  default = true
}

variable "vmid" {
  type    = number
  default = 0
}

variable "ostemplate" {
  type    = string
  default = "local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst"
}

variable "mount_points" {
  type = list(object({
    key     = number
    storage = string
    mp      = string
    size    = string
  }))
  default = []
}
