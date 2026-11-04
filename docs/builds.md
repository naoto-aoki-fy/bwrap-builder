# Build and runtime details

## Targets and prerequisites

The workflow uses Rocky project-maintained Docker Hub images
[`rockylinux/rockylinux:9` and `rockylinux/rockylinux:10`](https://hub.docker.com/r/rockylinux/rockylinux),
and Docker Official Images `ubuntu:24.04`, `ubuntu:26.04`, `debian:13`, `debian:12`, `debian:11`, and `alpine:3.24.3`.
The legacy `library/rockylinux` namespace is not used.
Alpine is pinned to **3.24.3**, the current stable patch release at implementation
([Alpine release list](https://alpinelinux.org/releases/)). Other images pin the
requested distribution release; tags and package repositories can receive updates.
This is a source-commit-pinned build, not a bit-for-bit reproducible toolchain.

Both architectures use native GitHub-hosted `ubuntu-24.04` / `ubuntu-24.04-arm`
runners, with Docker selecting the native image architecture. The repository must
have access to these labels; standard ARM runners are available for public repos.
Private repositories need an appropriate hosted ARM runner entitlement/label;
see [GitHub runner availability](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
No QEMU, self-hosted runner, privileged container, or setuid installation is used.

Rocky Linux 10's distribution CPU baseline also applies to its outputs. A filename
architecture alone does not promise support for every CPU of that architecture.

## Revision and build policy

The resolver clones all advertised upstream refs and history once. Exact tag names
win over hexadecimal interpretation, and annotated tags are peeled to a commit.
Otherwise 4–40 hexadecimal characters must identify exactly one fetched Git object,
and that object must be a commit. Branch names and revision expressions are rejected.
An unadvertised/unreachable upstream object is unsupported. Full history is required
to check abbreviated-hash ambiguity. The resolved 40-character SHA and `git archive`
snapshot are shared with all jobs. Input is passed via an environment variable and
Git argument arrays, never evaluated as shell code.

Dependencies are explicit in `scripts/install-deps.sh`. Rocky installation uses
`dnf -y --enablerepo=crb install`, retaining the default BaseOS and AppStream
repositories and enabling CRB for that transaction. No EPEL or downloaded build
tools are needed. [CRB is disabled by default on Rocky 9 and 10](https://github.com/rocky-linux/wiki.rockylinux.org/blob/main/docs/rocky/repo.md).
The packages are identical on x86_64 and aarch64:

| Repository | Required RPM packages |
| --- | --- |
| BaseOS | `pkgconf-pkg-config`, `python3`, `bash`, `file`, `binutils`, `util-linux` |
| AppStream | `gcc`, `libcap-devel`, `libselinux-devel` |
| CRB | `meson`, `ninja-build` |

The Dockerfile defaults to the maintained Rocky 9 image so its `FROM` is valid
without build arguments; the workflow still supplies each target's image explicitly.

SELinux is enabled on
Rocky/Ubuntu/Debian and disabled on Alpine; libcap is required everywhere. Tests are enabled,
manual-page generation is disabled, and shell completions retain upstream defaults.
No kernel version is assumed, no host CPU optimization is requested, and no patches
are applied. Older revisions offering a setuid option receive `-Dsetuid=false`.
Revisions without the required Meson options fail with a diagnostic; there is no
Autotools fallback or promise that every historical commit can build on every target.

Only dependency installation runs as container root. Upstream configuration,
compilation and tests run as the runner's non-root UID with no capabilities, no
network, no credentials, and no repository checkout mounted. Docker's default
seccomp policy and `no-new-privileges` remain in effect. Upstream sources are code:
only dispatch revisions you trust. The workflow token is read-only and checkout
credentials are not persisted. No repository secrets are forwarded to builds.

## Validation and diagnostics

Each job checks nonempty executable output, ELF type, ELF CPU architecture, absence
of setuid/setgid bits, `--version`, `--help`, loader dependencies (`ldd` and
`readelf`), missing libraries, and SHA-256. It then runs the complete upstream Meson
test suite. Upstream TAP skips and Meson logs preserve which tests passed versus
which could not run under namespace/kernel/container restrictions. Failures are
never automatically converted to environmental skips: an upstream version that
fails rather than skips in this environment makes the job fail. Consult its TAP
output before deciding whether a different runner environment is needed.

`fail-fast: false` attempts all 16 entries after successful resolution. Compilation,
validation, or test failure prevents the executable artifact upload. Diagnostics
upload and summaries are attempted even on failure. Resolution failure prevents all
builds because no valid source commit exists. Runner/image/package availability
and unsupported upstream revisions can also cause explicit failures.

The reports artifact includes source SHA, actual OS version, Meson options, file/ELF
metadata, runtime version/help, SHA-256, `ldd`, and Meson logs. No test result should
be inferred from a successful compilation alone.

## Outputs and collection

Executable names are `bwrap-{rocky9,rocky10,ubuntu24.04,ubuntu26.04,debian13,debian12,debian11,alpine}-{x86_64,aarch64}`.
Each correspondingly named Actions artifact contains exactly one raw ELF file.
Actions transports artifacts in ZIP containers; after download/extraction the file
itself is an ELF, not an archive or package. Actions does not preserve Unix mode
bits: run `chmod +x bwrap-*` after downloading. Reports are separate `reports-*`
artifacts, and source is in `upstream-source`. All expire after seven days.

A later job can depend on `build`, use `actions/download-artifact` with pattern
`bwrap-*` and `merge-multiple: true`, and collect all 16 filenames. The publishing job collects these artifacts only after the full matrix succeeds;
see [publishing](publishing.md). Retain upstream license notices and review upstream
licensing requirements before redistributing executables.

Outputs are dynamically linked for the target distribution. Typical direct
libraries are libc and libcap, plus libselinux on Rocky/Ubuntu/Debian; libselinux can add
transitive dependencies such as libpcre2. Alpine uses the musl loader, other targets
use glibc. The exact interpreter, NEEDED entries and resolved transitive libraries
for each build are recorded in `elf-dependencies.txt` and `ldd.txt`; those reports
are authoritative. Install the matching distribution runtime packages (`libcap`,
`libselinux` on Rocky; `libcap2`, `libselinux1` on Ubuntu/Debian; `libcap` on Alpine) and
libc. These are not portable static binaries. Successful help/version validation
does not prove a host allows user namespaces or actual sandbox creation.

## Local checks

Install the configuration-check dependency with
`python3 -m pip install PyYAML==6.0.2`.
Run `python3 -m unittest discover -s tests -v` and `bash -n scripts/build.sh` plus
`sh -n scripts/install-deps.sh`. With Docker, build the dependency image and invoke
the same container command as the workflow after running the resolver with
`UPSTREAM_REF` and `GITHUB_OUTPUT` set. A real Actions run is still needed to check
all 16 images, hosted runner availability, package installation, native compilation,
namespace-dependent upstream tests, artifact transfer and summaries.

Implementation-time local validation:

- Six resolver unit tests passed, using a temporary Git repository (including
  annotated tags, prefixes, rejected branches/injection strings, noncommit objects,
  and a simulated ambiguous-object lookup).
- Live resolution of `v0.13.1` produced
  `362936aea0d5c6e70f7af75d2d44b5a914cb4ba2`; source archive listing succeeded.
- Shell syntax checks, YAML parsing, ten-target uniqueness checks, actionlint,
  and Git whitespace checks passed.
- Docker was unavailable locally. No target compilation, binary execution, or
  upstream test suite has been run yet; those require the real matrix run.

### Rocky build repair validation (2026-11-04)

- Docker Registry manifests for both maintained tags advertised `linux/amd64`
  and `linux/arm64/v8`. Observed index digests were
  `sha256:8101994123cf3d0a8fee517bee7f39e555c7d92bd2d9eb3303cc988a0eeed00f`
  (9) and `sha256:827d37bc128288ccf160ee318bb3cb92d591164cb217e92f8bc61e3982ae1834`
  (10). These observations do not pin the mutable tags.
- Official `repodata/repomd.xml` and primary metadata under
  `https://dl.rockylinux.org/pub/rocky/{9,10}/{BaseOS,AppStream,CRB}/{x86_64,aarch64}/os/`
  contained every requested package for all four Rocky targets. CRB supplied
  Meson 0.63.3 / Ninja 1.10.2 on 9 and Meson 1.4.1 / Ninja 1.11.1 on 10.
  This checks package availability, not DNF dependency solving or installation.
- All 16 Python unit tests, both shell syntax checks, and actionlint 1.7.7
  validation of both workflows passed. New configuration
  tests exercise Rocky installer commands and failure propagation using a stub,
  enforce ten unique targets and native runner/image mappings, and check the
  publication success gate and publisher artifact-name agreement. The checks
  workflow runs these on pushes and pull requests.
- Docker and authenticated GitHub access were unavailable. Actual DNF resolution,
  installation and upstream `v0.13.1` builds on all ten native targets still require
  an Actions run. Confirm each named ELF, reports, checksum and test logs there;
  the previously reported one pass and five skips per target are not additional
  functional coverage. No new target binaries or diagnostics were produced locally.
- The publication gate and existing integrity checks are unchanged. Unit tests
  cover incomplete artifact sets and failed upload/verification paths, but an
  end-to-end failed-matrix publication check has not been run here.
