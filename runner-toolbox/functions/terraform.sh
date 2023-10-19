#!/bin/bash

export TF_STATEFILE_BASEDIR='/pve/terraform'

inject_tf_var_for_lxc() {
  local vmid="${1}"          ; check_null vmid "${1}"
  local output_folder="${2}" ; check_null output_folder "${2}"
  local var_name="${3}"      ; check_null var_name "${3}"

  local value
  local type
  value=$(lxc_config "${vmid}" ".container.${var_name}")
  type=$(lxc_config "${vmid}" ".container.${var_name} | type")
  [[ -n "${value}" && "${type}" == 'string' ]] && value="\"${value}\""
  [ -n "${value}" ] && echo "${var_name}=${value}" >> "${output_folder}/terraform.tfvars"
}

inject_tf_lxc_config() {
  local vmid="${1}"          ; check_null vmid "${1}"
  local output_folder="${2}" ; check_null output_folder "${2}"

  local keys
  keys=$(lxc_config "${vmid}" '.container | keys | @csv' | tr -d '"')
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

run_terraform_lxc() {
  local vmid="${1}"      ; check_null vmid "${1}"
  local tf_action="${2}" ; check_null tf_action "${2}"

  local tf_dir='terraform/lxc'
  local tf_statefile="${TF_STATEFILE_BASEDIR}/lxc-${vmid}.tfstate"

  inject_tf_lxc_config "${vmid}" "${tf_dir}"
  trap "rm -rf ${tf_dir}/terraform.tfvars ${tf_dir}/.terraform ${tf_dir}/.terraform.lock.hcl ${tf_dir}/tf_apply.plan ${tf_dir}/tf_destroy.plan" ERR RETURN

  pushd "${tf_dir}" > /dev/null
  
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
  esac

  popd > /dev/null
}
