resource "proxmox_vm_qemu" "vm" {
  target_node = "pve"
  vmid        = var.vmid
  name        = var.hostname

  clone      = var.template
  full_clone = true

  agent  = 1
  memory = var.memory
  # Attach the virtio-balloon device at floor == max. The device never
  # inflates (no reclamation), but its presence is what lets PVE read guest
  # memory usage — without it, the `mem` field falls back to the QEMU
  # process's host-side cgroup RSS, which tracks pages QEMU has touched,
  # not what the guest is actually using. qemu-guest-agent does not
  # populate this metric.
  balloon  = var.memory
  scsihw   = "virtio-scsi-single"
  onboot   = var.start_on_boot
  vm_state = "running"
  # The clone-from-template path resets boot order to net0 (PXE) unless we
  # set it explicitly; without this the VM PXE-loops forever instead of
  # booting the rootfs.
  boot = "order=scsi0"

  # Once `cpu` block is used, the top-level cores/sockets/cpu_type fields
  # are forbidden by the provider — moving them all inside the block is
  # the documented path forward.
  cpu {
    type    = "host"
    cores   = var.cpu_core_count
    sockets = var.cpu_socket_count
  }

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

  # Slot-keyed disks block. The legacy positional `disk { ... }` blocks
  # match by index and produce false slot-swap diffs when state and config
  # are read in different orders, so we use the new shape exclusively.
  disks {
    scsi {
      scsi0 {
        disk {
          size    = var.rootfs_size
          storage = var.storage
        }
      }
    }
    ide {
      ide2 {
        cloudinit {
          storage = var.storage
        }
      }
    }
  }

  # Slot-keyed usbs block. usb_passthrough is constrained to 1 entry by
  # the variable validation; adding usb1..usb4 here would be premature.
  usbs {
    dynamic "usb0" {
      for_each = length(var.usb_passthrough) > 0 ? [var.usb_passthrough[0]] : []
      content {
        device {
          device_id = usb0.value.host
        }
      }
    }
  }
}
