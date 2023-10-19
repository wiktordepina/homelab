#!/bin/bash

build_image() {
  local source_folder="${1}" ; check_null source_folder "${1}"
  local image_tag="${2}"     ; check_null image_tag "${2}"

  DOCKER_BUILDKIT=1 docker build "${source_folder}" -t "${image_tag}"
}
