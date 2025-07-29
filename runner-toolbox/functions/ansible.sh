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
