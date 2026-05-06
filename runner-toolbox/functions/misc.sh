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
