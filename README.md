# bubblewrap binary builder

Independently builds and distributes unmodified
[upstream bubblewrap](https://github.com/containers/bubblewrap) binaries.
These are not official upstream release assets.

Open **Actions → Build and publish upstream bubblewrap → Run workflow**.
Enter an exact upstream tag (for example `v0.13.1`) or an unambiguous commit SHA
in `upstream_ref`. Successful builds publish 16 raw executables: Rocky Linux 9/10,
Ubuntu 24.04/26.04, Debian 13/12/11, and Alpine Linux 3.24.3, each for x86_64 and aarch64.

Release tags use independent `vMAJOR.MINOR.PATCH` versions, starting at `v0.0.1`.
Download the matching executable from **Releases**, then:

```sh
chmod +x bwrap-ubuntu24.04-x86_64
./bwrap-ubuntu24.04-x86_64 --version
```

Binaries are dynamically linked to the target distro's libc and libcap, plus
libselinux on Rocky/Ubuntu/Debian. Alpine uses musl; the others use glibc. Sandbox creation
requires a Linux kernel and host policy that permit unprivileged user namespaces.

See [builds, runtime compatibility, failures, and retries](docs/builds.md) and
[publishing and licensing](docs/publishing.md). Review the
[upstream license](https://github.com/containers/bubblewrap/blob/main/COPYING)
before redistributing; upstream bubblewrap uses LGPL-2.0-or-later licensing.
