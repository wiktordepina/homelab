# Build the default VM template

VMs in this homelab clone from a Proxmox VM template; the default template is Debian 13 generic-cloud with cloud-init. Building it is a one-time, manual procedure on the Proxmox host. Subsequent VM provisioning through Terraform clones from this template and injects per-VM configuration through cloud-init at clone time.

This runbook produces the default. A future variant runbook will cover non-default templates (different distro, different cloud image flavour) when a workload needs one.

## When to do this

- **Bootstrap.** Before the first VM is provisioned in the homelab.
- **Refresh.** When the upstream cloud image picks up changes worth baking in. Mostly cosmetic, since clones run `apt update && apt upgrade` on first boot anyway.

If neither applies, do nothing.

## What you'll end up with

A Proxmox VM template at VMID `9000` named `tmpl-debian-13-cloudinit`, on `local-zpool` storage, with a cloud-init drive attached. Future `proxmox_vm_qemu` clones from this VMID inherit the disk and the cloud-init machinery; per-VM overrides (IP, hostname, SSH key) are injected at clone time, not baked into the template.

## Why these choices

- **VMID 9000.** Templates conventionally live in the `9000–9999` range so they do not collide with running guests (`100–599` in this homelab). `9000` is the default template; future variants take `9001`, `9002`, and so on.
- **Debian 13 generic-cloud.** The LXC fleet runs Debian; matching the OS reduces cognitive load. The `genericcloud` flavour is the right one for KVM (vs `nocloud` for bare-metal, or hypervisor-specific flavours for clouds we are not running).
- **`local-zpool` storage.** Same default as LXC rootfs, so VM disks and LXC rootfs share one ZFS pool.
- **`virtio-scsi-pci` controller.** Best-performing path for KVM disks; the cloud image works without additional drivers.

## Procedure

Run on the Proxmox host. SSH from a runner or directly:

```bash
ssh root@192.168.200.100
```

### 1. Download the cloud image

```bash
cd /root
curl -OL https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2
curl -OL https://cloud.debian.org/images/cloud/trixie/latest/SHA512SUMS
sha512sum -c --ignore-missing SHA512SUMS
```

Expect a single `debian-13-genericcloud-amd64.qcow2: OK` line. Anything else means the download is corrupt and the rest of the procedure must not proceed.

### 2. Create the template VM shell

```bash
qm create 9000 \
  --name tmpl-debian-13-cloudinit \
  --memory 1024 \
  --cores 1 \
  --net0 virtio,bridge=vmbr1 \
  --serial0 socket --vga serial0 \
  --agent enabled=1 \
  --ostype l26 \
  --cpu host \
  --machine q35
```

`--memory` and `--cores` here are placeholders. Clones override them from the per-VM YAML.

`vmbr1` is the homelab guest bridge (`vmbr0` is management-only and must not be attached). Clones override the bridge if they need a different one (e.g. multi-NIC services).

### 3. Import the disk

```bash
qm importdisk 9000 debian-13-genericcloud-amd64.qcow2 local-zpool
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-zpool:vm-9000-disk-0
```

`importdisk` converts the qcow2 to whatever format `local-zpool` uses (raw on ZFS) and registers it as an unattached volume. The `set` line attaches it as `scsi0`.

### 4. Attach the cloud-init drive and boot order

```bash
qm set 9000 --ide2 local-zpool:cloudinit
qm set 9000 --boot order=scsi0
```

The cloud-init drive is a tiny synthetic ISO that Proxmox regenerates each time `ipconfig0`, `sshkeys`, `ciuser`, etc. change on a clone.

### 5. Convert to template

```bash
qm template 9000
```

This marks the VM as a template. Its disk becomes the base for fast clones; new VMs cloned from it start as full copies (this homelab does not use linked clones — see *Notes*).

### 6. Verify

```bash
qm config 9000
```

Expect:

```
agent: enabled=1
boot: order=scsi0
cores: 1
cpu: host
ide2: local-zpool:cloudinit
machine: q35
memory: 1024
name: tmpl-debian-13-cloudinit
net0: virtio,bridge=vmbr1
ostype: l26
scsi0: local-zpool:vm-9000-disk-0
scsihw: virtio-scsi-pci
serial0: socket
template: 1
vga: serial0
```

The `template: 1` line confirms the conversion. Clean up the qcow2:

```bash
rm /root/debian-13-genericcloud-amd64.qcow2 /root/SHA512SUMS
```

## Refreshing the template

The standard refresh is drop-and-rebuild:

```bash
qm destroy 9000
# Then re-run the full procedure from step 1.
```

Existing VMs that were cloned from `9000` are unaffected because clones in this homelab are full clones — their disks have already diverged from the template's. Only new clones see the rebuilt image.

If a refresh ever has to preserve VMID `9000` exactly (e.g. terraform state references it by ID and you would rather not re-import), replace the disk in place:

```bash
qm set 9000 --delete scsi0
qm importdisk 9000 debian-13-genericcloud-amd64.qcow2 local-zpool
qm set 9000 --scsi0 local-zpool:vm-9000-disk-0
qm template 9000
```

Drop-and-rebuild is the default; reach for the in-place path only when there is a specific reason.

## Removing the template

```bash
qm destroy 9000
```

Succeeds as long as no linked clones reference it. This homelab uses full clones, so `destroy` should always work without further preparation. If it fails citing dependent volumes, something has been provisioned outside the IaC and must be reconciled manually.

## Notes

- **Cloud-init scope.** The template ships with no SSH key, no static IP, no hostname. All of that is injected at clone time by the `proxmox_vm_qemu` Terraform resource via cloud-init. Do not bake any of it into the template — every clone would inherit the same identity.
- **`qemu-guest-agent`.** Debian generic-cloud images include `qemu-guest-agent` preinstalled but **not** enabled — first boot does not start it. The `--agent enabled=1` flag in step 2 only declares the Proxmox-side expectation. Enabling and starting the service is done in the guest by the `base` Ansible role on first apply, gated on `ansible_virtualization_type == "kvm"` so LXCs are unaffected. Once running, it lets Proxmox query the VM for IP discovery, do clean shutdowns, and freeze the filesystem during backups.
- **Full vs linked clones.** Proxmox supports linked clones (clone-on-write from the template's base disk), but this homelab does not use them — they couple every VM's lifecycle to the template's, and the disk savings are negligible at our scale. Clones are full disks unless explicitly overridden.
- **Image freshness.** First-boot `apt upgrade` (run by cloud-init `package_upgrade: true` on the per-VM clone) catches up to current security state, so a slightly stale template is operationally equivalent to a fresh one. Refresh the template when you want new defaults baked in (newer kernel preinstalled, fewer first-boot upgrades), not as routine maintenance.
- **Do not run the template.** A running template is harmless to itself but Proxmox refuses to clone while it is running. Leave it stopped.
