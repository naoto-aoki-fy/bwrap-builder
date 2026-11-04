ARG BASE_IMAGE=rockylinux/rockylinux:9
FROM ${BASE_IMAGE}
ARG DISTRO
COPY install-deps.sh /install-deps.sh
RUN sh /install-deps.sh "$DISTRO" && rm /install-deps.sh
