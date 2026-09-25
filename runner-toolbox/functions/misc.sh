#!/bin/bash

# check_null - Check if the provided argument is null or empty.
#
# Description:
#   This function checks if the provided argument is null or empty.
# 
# Usage:
#   check_null <argument_name> <argument_value>
# 
# Parameters:
#   <argument_name>  - The name of the argument to be checked for null or emptiness.
#   <argument_value> - The value to be checked for null or emptiness.
# 
# Returns:
#   0 if the argument value is not null or empty.
#   1 if the argument value is null or empty.
#
# Example:
#   check_null 'city' "%{city}"
check_null() {
  local name="${1}"
  local value="${2}"
  [ -z "${value}" ] && echo "Value for '${name}' missing" && exit 1
}

# refuse_apply_runner - Stop if the VMID is an apply runner.
#
# Description:
#   Apply runners (600-699) are created and converged by the bootstrap,
#   never by these operations. A job runs on an apply runner, so a Terraform
#   replacement or an Ansible restart aimed at one can take out the machine
#   running the job. Imported into Terraform, one would plan exactly that
#   replacement: the provider does not read ostemplate or ssh_public_keys
#   back, and both force a new container.
#
# Usage:
#   refuse_apply_runner <vmid>
#
# Parameters:
#   <vmid> - The ID of the container about to be operated on.
refuse_apply_runner() {
  local vmid="${1}" ; check_null vmid "${1}"

  if [[ "${vmid}" =~ ^6[0-9]{2}$ ]]; then
    echo "VMID ${vmid} is an apply runner; use bootstrap/apply-runner, not this operation."
    exit 1
  fi
}

# lxc_config - Gets LXC (Linux Containers) settings.
#
# Description:
#   This function returns configuration for LXC containers.
#
# Usage:
#   lxc_config <vmid> <query>
#
# Parameters:
#   <vmid>  - The ID of the LXC container.
#   <query> - The query to be executed on the LXC configuration file.
#
# Returns:
#   The value of the query executed on the LXC configuration file.
#
# Example:
#   lxc_config 204 '.terraform.ip_address'
lxc_config() {
  local vmid="${1}"  ; check_null vmid "${1}"
  local query="${2}" ; check_null query "${2}"

  yq -r "${query}" "config/lxc/${vmid}.yaml"
}

# vm_config - Gets VM settings.
#
# Description:
#   This function returns configuration for a Proxmox QEMU VM.
#
# Usage:
#   vm_config <vmid> <query>
#
# Parameters:
#   <vmid>  - The ID of the VM.
#   <query> - The query to be executed on the VM configuration file.
#
# Returns:
#   The value of the query executed on the VM configuration file.
#
# Example:
#   vm_config 214 '.terraform.ip_address'
vm_config() {
  local vmid="${1}"  ; check_null vmid "${1}"
  local query="${2}" ; check_null query "${2}"

  yq -r "${query}" "config/vm/${vmid}.yaml"
}

# external_host_config - Gets external-host settings.
#
# Description:
#   This function returns configuration for an external host.
#
# Usage:
#   external_host_config <hostname> <query>
#
# Parameters:
#   <hostname> - The hostname of the external host.
#   <query>    - The query to be executed on the external-host configuration file.
#
# Returns:
#   The value of the query executed on the configuration file.
#
# Example:
#   external_host_config pi-01 '.identity.ip'
external_host_config() {
  local hostname="${1}" ; check_null hostname "${1}"
  local query="${2}"    ; check_null query "${2}"

  yq -r "${query}" "config/external-hosts/${hostname}.yml"
}
