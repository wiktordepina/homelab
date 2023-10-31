#!/bin/bash

export TF_STATEFILE_BASEDIR='/pve/terraform'

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
    echo "ssh_public_keys=\"$(cat config/worker_id_rsa.pub)\""
  } >> "${output_folder}/terraform.tfvars"
}

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

run_terraform_lxc() {
  local vmid="${1}"      ; check_null vmid "${1}"
  local tf_action="${2}" ; check_null tf_action "${2}"

  local tf_dir='terraform/lxc'
  local tf_statefile="${TF_STATEFILE_BASEDIR}/lxc-${vmid}.tfstate"

  inject_tf_lxc_config "${vmid}" "${tf_dir}"
  run_terraform "${tf_action}" "${tf_dir}" "${tf_statefile}"
}

run_terraform_dns() {
  local tf_action="${1}" ; check_null tf_action "${1}"
  check_null DNS_TSIG_KEY "${DNS_TSIG_KEY}"

  local tf_dir='terraform/dns'
  local tf_statefile="${TF_STATEFILE_BASEDIR}/dns-records.tfstate"
  echo "tsig_key=\"${DNS_TSIG_KEY}\"" > "${tf_dir}/terraform.tfvars"

  run_terraform "${tf_action}" "${tf_dir}" "${tf_statefile}"
}
