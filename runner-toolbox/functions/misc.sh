#!/bin/bash

check_null() {
  local name="${1}"
  local value="${2}"
  [ -z "${value}" ] && echo "Value for '${name}' missing" && exit 1
}

lxc_config() {
  local vmid="${1}"  ; check_null vmid "${1}"
  local query="${2}" ; check_null query "${2}"

  yq -r "${query}" "config/lxc/${vmid}/config.yaml"
}
