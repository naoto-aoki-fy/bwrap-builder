#!/bin/sh
set -eu
case "$1" in
  rocky9|rocky10)
    # Meson and Ninja are in Rocky's CRB repository (disabled by default).
    dnf -y --enablerepo=crb install gcc meson ninja-build pkgconf-pkg-config libcap-devel libselinux-devel python3 bash file binutils util-linux
    dnf clean all
    ;;
  ubuntu24.04|ubuntu26.04|debian13|debian12|debian11)
    if [ "$1" = debian11 ]; then
      # Replace both legacy and deb822 image defaults; never mix live and archive indexes.
      rm -f /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources
      cat > /etc/apt/sources.list <<'SOURCES'
deb [check-valid-until=no] http://archive.debian.org/debian bullseye main
deb [check-valid-until=no] http://archive.debian.org/debian-security bullseye-security main
SOURCES
      # Do not reuse indexes inherited from the base image.
      rm -rf /var/lib/apt/lists/*
    fi
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gcc libc6-dev meson ninja-build pkg-config libcap-dev libselinux1-dev python3 bash file binutils util-linux
    rm -rf /var/lib/apt/lists/*
    ;;
  alpine)
    apk add --no-cache build-base meson ninja pkgconf libcap-dev python3 bash file binutils util-linux
    ;;
  *) echo "Unknown distribution: $1" >&2; exit 1 ;;
esac
