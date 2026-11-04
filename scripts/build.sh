#!/usr/bin/env bash
set -Eeuo pipefail
distro=$1
arch=$2
sha=$3
report=/out/reports
mkdir -p "$report" /tmp/work/source
exec > >(tee "$report/build.log") 2>&1
trap 'rc=$?; echo "Build failed (exit $rc): distro=$distro arch=$arch commit=$sha; see build.log and Meson logs"; cp -r /tmp/work/build/meson-logs "$report/" 2>/dev/null || true; exit "$rc"' ERR
[[ $sha =~ ^[0-9a-f]{40}$ ]]
[[ $(uname -m) == "$arch" ]]
[[ $(cat /input/resolved-sha.txt) == "$sha" ]]
tar -xf /input/source.tar -C /tmp/work/source
cd /tmp/work
[[ -f source/meson.build ]] || { echo 'This revision has no Meson build; older Autotools revisions are unsupported.'; exit 1; }
selinux=enabled
[[ $distro != alpine ]] || selinux=disabled
# Only pass options present in this revision. Required options fail clearly if absent.
options=source/meson_options.txt
[[ -f $options ]] || options=source/meson.options
for required in selinux tests man; do
  grep -Eq "['\"]${required}['\"]" "$options" || { echo "Unsupported Meson revision: missing $required option"; exit 1; }
done
args=(-Dselinux="$selinux" -Dtests=true -Dman=disabled)
# Older Meson revisions offered a setuid install mode. Never enable it.
if grep -Eq "['\"]setuid['\"]" "$options"; then args+=(-Dsetuid=false); fi
meson setup build source --buildtype=release --wrap-mode=nodownload "${args[@]}"
meson compile -C build
name="bwrap-$distro-$arch"
binary="/out/$name"
install -m 0755 build/bwrap "$binary"
[[ -s $binary && -x $binary && ! -u $binary && ! -g $binary ]]
file "$binary" | tee "$report/file.txt"
readelf -h "$binary" | tee "$report/elf-header.txt"
grep -q 'ELF' "$report/file.txt"
grep -Eq 'Type:.*(EXEC|DYN)' "$report/elf-header.txt"
case "$arch" in
  x86_64) grep -q 'Machine:.*Advanced Micro Devices X86-64' "$report/elf-header.txt" ;;
  aarch64) grep -q 'Machine:.*AArch64' "$report/elf-header.txt" ;;
  *) exit 1 ;;
esac
"$binary" --version | tee "$report/version.txt"
"$binary" --help > "$report/help.txt"
readelf -l -d "$binary" > "$report/elf-dependencies.txt"
ldd "$binary" > "$report/ldd.txt" 2>&1
test -s "$report/ldd.txt"
if grep -q 'not found' "$report/ldd.txt"; then
  echo 'Mandatory validation failed: unresolved runtime libraries'; exit 1
fi
cat "$report/ldd.txt"
(cd /out && sha256sum "$name") > "$report/sha256.txt"
printf '%s\n' "$sha" > "$report/upstream-sha.txt"
cat /etc/os-release > "$report/os-release.txt"
meson configure build > "$report/meson-options.txt"
# Upstream TAP tests report environmental skips. Never reclassify failures as skips.
meson test -C build --print-errorlogs
cp -r build/meson-logs "$report/"
printf 'Validated %s at %s\n' "$name" "$sha" > "$report/result.txt"
