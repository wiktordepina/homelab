ARG BASE_IMAGE_TAG=12

FROM debian:${BASE_IMAGE_TAG}

WORKDIR /toolbox

ARG TERRAFORM_VERSION=1.12.2
ARG HCLEDIT_VERSION=0.2.17
ARG UV_VERSION=0.8.4

ENV LANG=en_GB.UTF-8
ENV LC_ALL=en_GB.UTF-8
ENV LANGUAGE=en_GB.UTF-8

COPY .python-version pyproject.toml uv.lock /toolbox

RUN <<SETUP
  set -e
  apt-get update
  # => set locales
  echo UTC > /etc/timezone
  apt-get install --no-install-recommends -y apt-utils locales
  sed -i 's/^# *\(en_GB.UTF-8\)/\1/' /etc/locale.gen
  locale-gen
  # => get dependencies
  apt-get install --no-install-recommends -y \
    jq \
    ssh \
    unzip \
    curl \
    git \
    gnupg \
    wget \
    software-properties-common
  # => setup uv and ansible
  wget -O- "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" | \
    tar -xz --directory /tmp
  cp /tmp/uv-x86_64-unknown-linux-gnu/* /usr/bin/
  uv sync
  uv run ansible-galaxy collection install community.docker
  # => setup terraform
  wget -O- https://apt.releases.hashicorp.com/gpg | \
  gpg --dearmor | \
  tee /usr/share/keyrings/hashicorp-archive-keyring.gpg
  gpg --no-default-keyring \
    --keyring /usr/share/keyrings/hashicorp-archive-keyring.gpg \
    --fingerprint
  git clone https://github.com/tfutils/tfenv.git ~/.tfenv
  ln -s ~/.tfenv/bin/* /usr/local/bin
  tfenv install "${TERRAFORM_VERSION}"
  tfenv use "${TERRAFORM_VERSION}"
  # => setup hcledit
  wget -O- "https://github.com/minamijoyo/hcledit/releases/download/v${HCLEDIT_VERSION}/hcledit_${HCLEDIT_VERSION}_linux_amd64.tar.gz" | \
    tar -xz --directory /usr/local/bin
  chmod 755 /usr/local/bin/hcledit
  # => cleanup
  rm -rf /tmp/**
SETUP

ENV PATH="/toolbox/.venv/bin:$PATH"
                  
COPY ./functions /opt/functions
COPY ./scripts /usr/bin
COPY ./provider/terraform-provider-proxmox /root/.terraform.d/plugins/terraform.local/telmate/proxmox/1.0.0/linux_amd64/terraform-provider-proxmox_v1.0.0
