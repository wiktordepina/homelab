#!/bin/bash

export ANSIBLE_CONFIG='/build/ansible/.ansible.cfg'

# run_ansible_lxc - Run Ansible inside an LXC container.
#
# Description:
#   This function runs Ansible inside an LXC container.
#   It sets up the necessary environment and executes the Ansible commands
#   within the specified LXC container. 
#   Ansible playbook is automatically generated from the config file for specified container.
#
# Usage:
#   run_ansible_lxc <vmid>
#
# Parameters:
#   <vmid> - The ID of the LXC container where the playbook will be run.
#
# Example:
#   run_ansible_lxc 204
run_ansible_lxc() {
  local vmid="${1}" ; check_null vmid "${1}"

  local lxc_ip
  lxc_ip=$(lxc_config "${vmid}" ".terraform.ip_address")
  lxc_ip="${lxc_ip%/*}"

  render_lxc_playbook "${vmid}" > playbook.yaml
  trap 'rm -rf /build/playbook.yaml' EXIT

  ansible-playbook -i "192.168.200.100,${lxc_ip}," playbook.yaml
}

run_ansible_pve() {
  ansible-playbook -i "192.168.200.100," config/pve/playbook.yaml
}

# run_ansible_vm - Run Ansible against a Proxmox QEMU VM.
#
# Description:
#   Mirror of run_ansible_lxc, targeting config/vm/<vmid>.yaml. Renders the
#   playbook via render_vm_playbook and applies it over SSH on the VM's IP.
#
# Usage:
#   run_ansible_vm <vmid>
#
# Parameters:
#   <vmid> - The VMID.
#
# Example:
#   run_ansible_vm 214
run_ansible_vm() {
  local vmid="${1}" ; check_null vmid "${1}"

  local vm_ip
  vm_ip=$(vm_config "${vmid}" ".terraform.ip_address")
  vm_ip="${vm_ip%/*}"

  render_vm_playbook "${vmid}" > playbook.yaml
  trap 'rm -rf /build/playbook.yaml' EXIT

  ansible-playbook -i "${vm_ip}," playbook.yaml
}

# run_ansible_external_host - Run Ansible against an external (non-LXC) host.
#
# Description:
#   This function runs Ansible against an external host declared under
#   config/external-hosts/. The playbook is generated from the host's
#   configuration file by render_external_host_playbook.
#
# Usage:
#   run_ansible_external_host <hostname>
#
# Parameters:
#   <hostname> - The hostname of the external host (matches the file name
#                under config/external-hosts/, without the .yml suffix).
#
# Example:
#   run_ansible_external_host pi-01
run_ansible_external_host() {
  local hostname="${1}" ; check_null hostname "${1}"

  local host_ip ssh_user
  host_ip=$(external_host_config "${hostname}" ".identity.ip")
  ssh_user=$(external_host_config "${hostname}" ".identity.ssh_user")

  render_external_host_playbook "${hostname}" > playbook.yaml
  trap 'rm -rf /build/playbook.yaml' EXIT

  ansible-playbook -i "${host_ip}," -u "${ssh_user}" playbook.yaml
}
