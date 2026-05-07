resource "proxmox_lxc" "container" {
  target_node     = "pve"
  ostemplate      = var.ostemplate
  hostname        = var.hostname
  cores           = var.cpu_core_count
  memory          = var.memory
  nameserver      = var.nameserver
  onboot          = var.start_on_boot
  password        = var.root_password
  ssh_public_keys = var.ssh_public_keys
  start           = var.start_after_creation
  swap            = var.swap
  unprivileged    = var.unprivileged
  vmid            = var.vmid

  rootfs {
    storage = var.storage
    size    = var.rootfs_size
  }

  features {
    keyctl  = var.enable_keyctl
    nesting = var.enable_nesting
  }

  network {
    name   = "eth0"
    bridge = var.network_bridge
    ip     = var.ip_address
    gw     = var.gateway
  }

  dynamic "network" {
    for_each = { for i, n in var.extra_networks : i => n }
    content {
      name   = "eth${network.key + 1}"
      bridge = network.value.bridge
      tag    = network.value.tag
      ip     = network.value.ip
      gw     = network.value.gw
    }
  }

  dynamic "mountpoint" {
    for_each = { for mp in var.mount_points : mp.key => mp }
    content {
      key     = mountpoint.key
      slot    = mountpoint.key
      storage = mountpoint.value.storage
      volume  = mountpoint.value.storage
      mp      = mountpoint.value.mp
      size    = mountpoint.value.size
    }
  }
}
