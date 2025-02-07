ARG BASE_IMAGE_TAG=24.04

FROM ubuntu:${BASE_IMAGE_TAG}

ARG TERRAFORM_VERSION=1.10.4
ARG HCLEDIT_VERSION=0.2.15

ENV LANG=en_GB.UTF-8
ENV LC_ALL=en_GB.UTF-8
ENV LANGUAGE=en_GB.UTF-8

RUN <<SETUP
set -e
  echo UTC > /etc/timezone
  apt-get update
  apt-get install --no-install-recommends -y readline-common apt-utils 
  apt-get install --no-install-recommends -y locales
  locale-gen en_GB.UTF-8
  update-locale LANG=en_GB.UTF-8
  apt-get install --no-install-recommends -y \
    jq \
    yq \
    python3-full \
    python3-pip \
    python3-ruamel.yaml \
    ansible \
    unzip \
    curl \
    git \
    gnupg \
    wget \
    software-properties-common
  ansible-galaxy collection install community.docker
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
  wget -O- "https://github.com/minamijoyo/hcledit/releases/download/v${HCLEDIT_VERSION}/hcledit_${HCLEDIT_VERSION}_linux_amd64.tar.gz" | \
    tar -xz --directory /usr/local/bin
  chmod 755 /usr/local/bin/hcledit
SETUP
                  
COPY ./functions /opt/functions
COPY ./scripts /usr/bin
