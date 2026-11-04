#!/bin/sh
set -eu
case "$1" in
  rocky9|rocky10)
    dnf -y install gcc meson ninja-build pkgconf-pkg-config libcap-devel libselinux-devel python3 bash file binutils util-linux
    dnf clean all
    ;;
  ubuntu24.04|ubuntu26.04)
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gcc libc6-dev meson ninja-build pkg-config libcap-dev libselinux1-dev python3 bash file binutils util-linux
    rm -rf /var/lib/apt/lists/*
    ;;
  alpine)
    apk add --no-cache build-base meson ninja pkgconf libcap-dev python3 bash file binutils util-linux
    ;;
  *) echo "Unknown distribution: $1" >&2; exit 1 ;;
esac
