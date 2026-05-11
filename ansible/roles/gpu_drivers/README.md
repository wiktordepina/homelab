# gpu_drivers

NVIDIA proprietary driver installation via Debian's non-free repo, using the Tesla 535 LTSB packages.

## Description

Installs the NVIDIA driver in one of two modes, auto-selected by host type:

- **Bare metal (PVE host)** — kernel headers for the running kernel series, the `nvidia-tesla-535-driver` metapackage (pulls userspace + persistence daemon), and `nvidia-tesla-535-kernel-dkms` (the DKMS-built kernel module). DKMS rebuilds the module on every kernel point upgrade because the headers metapackage tracks the series.
- **LXC** — userspace only: `nvidia-tesla-535-smi`, `libnvidia-tesla-535-encode1` (NVENC), `libnvidia-tesla-535-nvcuvid1` (NVDEC). The kernel module is supplied by the host via bind-mounted `/dev/nvidia*` device files declared in the container's `pve_extra` section.

Same source on host and LXC keeps the kernel module and userspace libs in lockstep — the userspace ABI is versioned and a mismatch breaks `nvidia-smi`, NVENC, and CUDA workloads.

## Why Tesla 535 specifically

Tesla 535 is NVIDIA's **Long-Term Support Branch (LTSB)**. It is the only currently-maintained branch that:

- Still supports older GPU generations the homelab uses (Pascal P-series Quadro, GTX 10xx).
- Tracks current kernel ABI changes (builds cleanly on Debian trixie's 6.17 PVE kernel).

The other available options were ruled out:
- Debian non-free's standard `nvidia-driver` (550.x in trixie) fails to build against kernel 6.17 — the DRM API changed.
- NVIDIA's CUDA apt repo for `debian13` only ships branches 590+, which dropped Pascal support.
- NVIDIA's CUDA apt repo for `debian12` ships 580 (which would work) but its signing key uses SHA1 self-certification, which Debian's apt rejects since policy tightened in early 2026.

When NVIDIA eventually drops Tesla 535 LTSB or the homelab's GPU is replaced with something current, revisit this choice.

## Variables

- `gpu_drivers_install_kernel_module` — whether to install the kernel module and headers. Defaults to `true` on bare metal, `false` inside an LXC. Override only when you need to force one mode.

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

- The role tracks the running kernel by *series* (`6.17`), not by exact point release. Point-release upgrades within a series rebuild the DKMS module automatically. Series jumps (e.g. 6.17 → 7.0) are not pulled — when ready to change series, install the new `proxmox-headers-<series>` and verify the driver builds against it.
- `nvidia-container-toolkit` (separate role) is only needed inside LXCs that run Docker workloads with GPU access. It is not used by Jellyfin (native install).
