# gpu_drivers

NVIDIA proprietary driver installation, sourced from NVIDIA's CUDA apt repo (Debian 13).

## Description

Installs the NVIDIA driver in one of two modes, auto-selected by host type:

- **Bare metal (PVE host)** — kernel headers (tracking the running kernel via `proxmox-default-headers`), DKMS-built kernel module, full userspace, and the persistence daemon. DKMS rebuilds the module on every kernel upgrade.
- **LXC** — userspace only (`nvidia-driver-cuda` and the libs it pulls: `libnvidia-encode1`, `libnvcuvid1`, `nvidia-smi`, `nvidia-persistenced`). The kernel module is supplied by the host via bind-mounted `/dev/nvidia*` device files declared in the container's `pve_extra` section.

Both modes use the same apt source so kernel-module and userspace versions stay locked together — userspace libs talk to the kernel module via a versioned ABI and a mismatch breaks `nvidia-smi`, NVENC, and CUDA workloads.

## Variables

- `gpu_drivers_install_kernel_module` — whether to install the kernel module and headers. Defaults to `true` on bare metal, `false` inside an LXC. Override only when you need to force one mode (e.g. test the userspace path on a bare-metal box).
- `gpu_drivers_nvidia_repo_base` — base URL of the NVIDIA CUDA apt repo. Defaults to NVIDIA's debian13 path.
- `gpu_drivers_branch` — driver branch to pin via `nvidia-driver-pinning-<branch>`. Defaults to `"590"` to keep Pascal-era cards (P2000) supported. Set to `""` to take whatever `cuda-drivers` resolves to (currently 595).

## Dependencies

- `base`

## Example usage

On the PVE host (`config/pve/playbook.yaml`):

```yaml
- name: PVE Extras
  hosts: 192.168.200.100
  roles:
    - gpu_drivers
```

In an LXC that needs GPU access (`config/lxc/<vmid>.yaml`):

```yaml
terraform:
  unprivileged: false  # required for device passthrough

pve_extra:
  - lxc.cgroup2.devices.allow: c 195:* rwm
  - lxc.cgroup2.devices.allow: c 234:* rwm
  - lxc.cgroup2.devices.allow: c 238:* rwm
  - lxc.mount.entry: /dev/nvidia0 dev/nvidia0 none bind,optional,create=file
  - lxc.mount.entry: /dev/nvidiactl dev/nvidiactl none bind,optional,create=file
  - lxc.mount.entry: /dev/nvidia-uvm dev/nvidia-uvm none bind,optional,create=file
  - lxc.mount.entry: /dev/nvidia-uvm-tools dev/nvidia-uvm-tools none bind,optional,create=file

ansible:
  roles:
    - base
    - gpu_drivers
    - jellyfin
```

## Notes

- The NVIDIA CUDA repo for debian13 currently ships driver branches 590, 595, and 610. The role pins to 590 by default (see `gpu_drivers_branch`); when NVIDIA drops Pascal from 590, raise the pin to the highest branch that still supports the cards in use.
- The host install also brings in `proxmox-headers-{{ ansible_kernel }}` for the running kernel alongside `proxmox-default-headers`, so DKMS can build the module immediately without waiting for a reboot into whatever kernel `proxmox-default-headers` happens to track.
- `nvidia-container-toolkit` (separate role) is only needed inside LXCs that run Docker workloads with GPU access. It is not used by Jellyfin (native install).
