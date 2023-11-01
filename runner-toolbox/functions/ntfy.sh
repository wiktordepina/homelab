#!/bin/bash

export NTFY_HOST='http://ntfy.home.matagoth.com'

ntfy_msg() {
  local topic="${1}"   ; check_null topic "${1}"
  local title="${2}"   ; check_null title "${2}"
  local message="${3}" ; check_null message "${3}"
  local tags="${4}"
  local extra_header="${5}"

  local headers="-H 'Title: ${title}'"
  [[ -n "${tags}" ]] && headers+=" -H 'Tags: ${tags}'"
  [[ -n "${extra_header}" ]] && headers+=" -H '${extra_header}'"

  eval "curl -u ${NTFY_CREDS} ${headers} -d '${message}' ${NTFY_HOST}/${topic}"
}

run_ntfy_workflow_status() {
  local wf_name="${1}"   ; check_null wf_name "${1}"
  local wf_status="${2}" ; check_null wf_status "${2}"
  local wf_url="${3}"    ; check_null wf_url "${3}"

  local status_tag='x,hankey'
  [[ "${wf_status}" == 'success' ]] && status_tag='white_check_mark,tada'

  local extra_header="Actions: view, Show workflow, ${wf_url}, clear=true"

  ntfy_msg 'gh-worker' "${wf_name}" "Workflow ${wf_name} completed with status ${wf_status}" "${status_tag}" "${extra_header}"
}
