ARG BASE_IMAGE_TAG=12.2
ARG TERRAFORM_VERSION=1.6.1

FROM debian:${BASE_IMAGE_TAG}

RUN apt update && apt upgrade -y

# ansible
RUN apt-get install -y python3-full python3-pip ansible

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
