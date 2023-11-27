#!/bin/bash

export ANSIBLE_CONFIG='/build/ansible/.ansible.cfg'

run_ansible_lxc() {
  local vmid="${1}" ; check_null vmid "${1}"

  local lxc_ip
  lxc_ip=$(lxc_config "${vmid}" ".terraform.ip_address")
  lxc_ip="${lxc_ip%/*}"

  render_lxc_playbook "${vmid}" > playbook.yaml
  trap 'rm -rf /build/playbook.yaml' EXIT

  ansible-playbook -i "192.168.200.100,${lxc_ip}," playbook.yaml
}
