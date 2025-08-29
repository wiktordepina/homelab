#!/bin/bash

export TF_STATEFILE_BASEDIR='/pve/terraform'

# inject_tf_var_for_lxc - Injects Terraform variables for LXC containers.
#
# Description:
#   This function injects Terraform variables for LXC containers.
#
# Usage:
#   inject_tf_var_for_lxc <vmid> <output_folder> <var_name>
#
# Parameters:
#   <vmid>          - The ID of the LXC container.
#   <output_folder> - The folder where the Terraform variables will be stored.
#   <var_name>      - The name of the variable to be injected.
#
# Example:
#   inject_tf_var_for_lxc 204 '/build' 'ip_address'
inject_tf_var_for_lxc() {
  local vmid="${1}"          ; check_null vmid "${1}"
  local output_folder="${2}" ; check_null output_folder "${2}"
  local var_name="${3}"      ; check_null var_name "${3}"

  local value
  local type
  value=$(lxc_config "${vmid}" ".terraform.${var_name}")
  type=$(lxc_config "${vmid}" ".terraform.${var_name} | type")
  [[ -n "${value}" && "${type}" == 'string' ]] && value="\"${value}\""
  [ -n "${value}" ] && echo "${var_name}=${value}" >> "${output_folder}/terraform.tfvars"
}

# inject_tf_lxc_config - Injects set of Terraform variables for LXC containers from config.
#
# Description:
#   This function injects set of Terraform variables for LXC containers from config.
#
# Usage:
#   inject_tf_lxc_config <vmid> <output_folder>
#
# Parameters:
#   <vmid>          - The ID of the LXC container.
#   <output_folder> - The folder where the Terraform variables will be stored.
inject_tf_lxc_config() {
  local vmid="${1}"          ; check_null vmid "${1}"
  local output_folder="${2}" ; check_null output_folder "${2}"

  local keys
  keys=$(lxc_config "${vmid}" '.terraform | keys | @csv' | tr -d '"')
  IFS=',' read -ra keys <<< "${keys}"
  for key in "${keys[@]}"; do
    inject_tf_var_for_lxc "${vmid}" "${output_folder}" "${key}" 
  done
  {
    echo "root_password=\"${PM_PASS}\""
    echo "start_after_creation=true"
    echo "ssh_public_keys = <<-EOT"
    echo "$(cat config/worker_id_rsa.pub)"
    echo "$(cat config/root_pve_id_rsa.pub)"
    echo "EOT"
  } >> "${output_folder}/terraform.tfvars"
}

# run_terraform - Run Terraform scripts.
#
# Description:
#   This function runs Terraform scripts.
#
# Usage:
#   run_terraform <tf_action> <tf_dir> <tf_statefile>
#
# Parameters:
#   <tf_action>    - The action to be performed by Terraform (plan|apply|plan_destroy|destroy).
#   <tf_dir>       - The directory where the Terraform scripts are stored.
#   <tf_statefile> - The statefile for the Terraform scripts.
#
# Example:
#   run_terraform 'plan' 'terraform/lxc' '/pve/terraform/lxc-204.tfstate'
run_terraform() {
  local tf_action="${1}"    ; check_null tf_action "${1}"
  local tf_dir="${2}"       ; check_null tf_dir "${2}"
  local tf_statefile="${3}" ; check_null tf_statefile "${3}"

  local tf_dir_absolute="$(pwd)/${tf_dir}"

  trap "rm -rf ${tf_dir_absolute}/terraform.tfvars ${tf_dir_absolute}/.terraform ${tf_dir_absolute}/.terraform.lock.hcl ${tf_dir_absolute}/tf_apply.plan ${tf_dir_absolute}/tf_destroy.plan" EXIT

  pushd "${tf_dir}" > /dev/null
  
  set -e

  terraform init --backend-config=path="${tf_statefile}"
  terraform validate

  case "${tf_action}" in
    plan)
      terraform plan -input=false --var-file terraform.tfvars -out tf_apply.plan
      ;;
    apply)
      terraform plan -input=false --var-file terraform.tfvars -out tf_apply.plan
      terraform apply --auto-approve -input=false tf_apply.plan
      ;;
    plan_destroy)
      terraform plan -destroy -input=false --var-file terraform.tfvars -out tf_destroy.plan
      ;;
    destroy)
      terraform plan -destroy -input=false --var-file terraform.tfvars -out tf_destroy.plan
      terraform apply --auto-approve -input=false tf_destroy.plan
      ;;
    *)
      echo "Unknown action - ${tf_action}"
      exit 1
  esac

  popd > /dev/null
}

# run_terraform_lxc - Run Terraform scripts for LXC containers.
#
# Description:
#   This function runs Terraform scripts for LXC containers.
#
# Usage:
#   run_terraform_lxc <vmid> <tf_action>
#
# Parameters:
#   <vmid>      - The ID of the LXC container.
#   <tf_action> - The action to be performed by Terraform (plan|apply|plan_destroy|destroy).
#
# Example:
#   run_terraform_lxc 204 'plan'
run_terraform_lxc() {
  local vmid="${1}"      ; check_null vmid "${1}"
  local tf_action="${2}" ; check_null tf_action "${2}"

  local tf_dir='terraform/lxc'
  local tf_statefile="${TF_STATEFILE_BASEDIR}/lxc-${vmid}.tfstate"

  inject_tf_lxc_config "${vmid}" "${tf_dir}"
  run_terraform "${tf_action}" "${tf_dir}" "${tf_statefile}"
}

# run_terraform_dns - Run Terraform scripts for DNS records.
#
# Description:
#   This function runs Terraform scripts for DNS records.
#
# Usage:
#   run_terraform_dns <tf_action>
#
# Parameters:
#   <tf_action> - The action to be performed by Terraform (plan|apply|plan_destroy|destroy).
#
# Example:
#   run_terraform_dns 'plan'
run_terraform_dns() {
  local tf_action="${1}" ; check_null tf_action "${1}"
  check_null DNS_TSIG_KEY "${DNS_TSIG_KEY}"

  local tf_dir='terraform/dns'
  local tf_statefile="${TF_STATEFILE_BASEDIR}/dns-records.tfstate"
  echo "tsig_key=\"${DNS_TSIG_KEY}\"" > "${tf_dir}/terraform.tfvars"

  run_terraform "${tf_action}" "${tf_dir}" "${tf_statefile}"
}
