FROM mcr.microsoft.com/devcontainers/base:trixie

RUN apt-get update ;\
        apt-get install --no-install-recommends --no-install-suggests -y \
                squashfs-tools ;\
        apt-get clean ;\
        rm -vrf /var/lib/apt/lists/*
