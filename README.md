# bubblewrap binary builder

Builds unmodified [upstream bubblewrap](https://github.com/containers/bubblewrap)
for Rocky Linux 9/10, Ubuntu 24.04/26.04, and Alpine, on native x86_64 and ARM64 runners.

In GitHub Actions, run **Build upstream bubblewrap** and enter an exact upstream
tag (for example `v0.13.1`) or an unambiguous commit hash as `upstream_ref`.
Download the ten temporary executable artifacts from the completed run.
No GitHub Releases are published.

See [build, validation, and runtime details](docs/builds.md).
