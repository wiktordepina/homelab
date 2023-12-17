ARG BASE_IMAGE_TAG=12.2

FROM debian:${BASE_IMAGE_TAG}

ARG TERRAFORM_VERSION=1.6.2
ARG HCLEDIT_VERSION='0.2.10'

RUN apt update && apt upgrade -y
RUN apt-get install -y jq yq

# ansible
RUN apt-get install -y python3-full python3-pip python3-ruamel.yaml ansible

# terraform
RUN apt-get install -y unzip curl git gnupg software-properties-common
RUN wget -O- https://apt.releases.hashicorp.com/gpg | \
    gpg --dearmor | \
    tee /usr/share/keyrings/hashicorp-archive-keyring.gpg 
RUN gpg --no-default-keyring \
    --keyring /usr/share/keyrings/hashicorp-archive-keyring.gpg \
    --fingerprint
RUN git clone https://github.com/tfutils/tfenv.git ~/.tfenv && \
    ln -s ~/.tfenv/bin/* /usr/local/bin && \
    tfenv install ${TERRAFORM_VERSION} && \
    tfenv use ${TERRAFORM_VERSION}

# hcledit
RUN wget -O- https://github.com/minamijoyo/hcledit/releases/download/v${HCLEDIT_VERSION}/hcledit_${HCLEDIT_VERSION}_linux_amd64.tar.gz | tar -xz --directory /usr/local/bin \
    && chmod 755 /usr/local/bin/hcledit
                  
COPY ./functions /opt/functions
COPY ./scripts /usr/bin
COPY entrypoint /opt/entrypoint
