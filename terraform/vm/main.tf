resource "proxmox_vm_qemu" "vm" {
  target_node = "pve"
  vmid        = var.vmid
  name        = var.hostname

  clone      = var.template
  full_clone = true

  agent    = 1
  cpu_type = "host"
  sockets  = var.cpu_socket_count
  cores    = var.cpu_core_count
  memory   = var.memory
  scsihw   = "virtio-scsi-pci"
  onboot   = var.start_on_boot
  vm_state = "running"

  os_type    = "cloud-init"
  ipconfig0  = "ip=${var.ip_address},gw=${var.gateway}"
  nameserver = var.nameserver
  ciuser     = "root"
  sshkeys    = var.ssh_public_keys

  network {
    id     = 0
    model  = "virtio"
    bridge = var.network_bridge
  }

  dynamic "network" {
    for_each = { for i, n in var.extra_networks : i => n }
    content {
      id     = network.key + 1
      model  = "virtio"
      bridge = network.value.bridge
      tag    = network.value.tag
    }
  }

  disk {
    slot    = "scsi0"
    type    = "disk"
    storage = var.storage
    size    = var.rootfs_size
  }

  disk {
    slot    = "ide2"
    type    = "cloudinit"
    storage = var.storage
  }

  dynamic "usb" {
    for_each = { for i, u in var.usb_passthrough : i => u }
    content {
      id   = usb.key
      host = usb.value.host
    }
  }
}
