#!/bin/bash

check_null() {
  local name="${1}"
  local value="${2}"
  [ -z "${value}" ] && echo "Value for '${name}' missing" && exit 1
}
