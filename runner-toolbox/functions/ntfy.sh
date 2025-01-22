#!/bin/bash

export NTFY_HOST='http://ntfy.home.matagoth.com'


# ntfy_msg - Send a message to the ntfy service.
#
# Description:
#   This function sends a message to the ntfy service.
#
# Usage:
#   ntfy_msg <topic> <title> <message> [<tags>] [<extra_header>]
#
# Parameters:
#   <topic>         - The topic to which the message will be sent.
#   <title>         - The title of the message.
#   <message>       - The content of the message.
#   <tags>          - The tags to be added to the message. [optional]
#   <extra_header>  - Extra headers to be added to the message. [optional]
#
# Returns:
#   The response from the ntfy service.
#
# Example:
#   ntfy_msg 'gh-worker' 'Workflow' 'Workflow completed' 'success'
ntfy_msg() {
  local topic="${1}"   ; check_null topic "${1}"
  local title="${2}"   ; check_null title "${2}"
  local message="${3}" ; check_null message "${3}"
  local tags="${4}"
  local extra_header="${5}"

  local headers="-H 'Title: ${title}'"
  [[ -n "${tags}" ]] && headers+=" -H 'Tags: ${tags}'"
  [[ -n "${extra_header}" ]] && headers+=" -H '${extra_header}'"

  local command="curl -u ${NTFY_CREDS} ${headers} -d '${message}' ${NTFY_HOST}/${topic}"
  eval $command
}

# run_ntfy_workflow_status - Send a message to the ntfy service with the workflow status.
#
# Description:
#   This function sends a message to the ntfy service with the workflow status.
#
# Usage:
#   run_ntfy_workflow_status <wf_name> <wf_status> <wf_url>
#
# Parameters:
#   <wf_name>   - The name of the workflow.
#   <wf_status> - The status of the workflow.
#   <wf_url>    - The URL of the workflow.
#
# Example:
#   run_ntfy_workflow_status 'workflow' 'success' 'https://github.com/wiktordepina/homelab/actions/runs/12917019032'
run_ntfy_workflow_status() {
  local wf_name="${1}"   ; check_null wf_name "${1}"
  local wf_status="${2}" ; check_null wf_status "${2}"
  local wf_url="${3}"    ; check_null wf_url "${3}"

  local status_tag='x,hankey'
  [[ "${wf_status}" == 'success' ]] && status_tag='white_check_mark,tada'

  local extra_header="Actions: view, Show workflow, ${wf_url}, clear=true"

  ntfy_msg 'gh-worker' "${wf_name}" "Workflow ${wf_name} completed with status ${wf_status}" "${status_tag}" "${extra_header}"
}
