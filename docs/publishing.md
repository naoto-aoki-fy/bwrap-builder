# Publishing

The `publish` job requires successful `resolve` and `build` jobs. A failed or
cancelled matrix entry skips publishing. Only this job has `contents: write`;
it uses the default `GITHUB_TOKEN`, never a personal token. The token is only
passed to the publishing step, and downloaded executables are never executed there.

Exact upstream tags produce `bwrap-<tag>` (including any upstream tag path
components). Commit inputs produce `bwrap-g<first-12-of-full-SHA>`, independent of
input abbreviation or case. Generated tags are checked with `git check-ref-format`.
An upstream tag takes precedence over a hexadecimal commit interpretation.
Distribution tags identify the builder workflow commit; release notes record the
actual upstream SHA and source link. They are not copies of upstream Git history.

Publishing uses a concurrency group keyed by the resolved release tag, with
`cancel-in-progress: false`. Concurrent attempts for that release serialize.
GitHub may replace older pending jobs in a concurrency group; rerun those if needed.

## Verification and existing releases

Artifact directories remain separate so merging cannot hide duplicate files.
The publisher requires exactly the ten expected artifact names and exactly one
correctly named executable inside each. It checks source SHA reports, recorded
SHA-256 checksums, nonempty ELF64 headers, executable type and CPU architecture,
and parses the ELF with `readelf`. It does not execute ARM binaries on x86 runners.

Both existing releases (including drafts) and existing distribution Git tags cause
an explicit failure. A 12-character SHA-prefix collision therefore cannot replace
an unrelated release. No assets are overwritten and there is no automatic delete.

After validation, a draft is created, exactly ten raw executables are uploaded,
and the remote asset list is checked for count, names and upload state. All assets
are downloaded again and checked against the original checksums and architectures.
Only then is the draft published. Checksum text lives in the release notes, not an
eleventh asset. GitHub's automatically generated source archive links are not
uploaded release assets and contain builder repository source.

Upload or verification failure leaves an unpublished draft. If the final publication
request succeeds but its response is lost, the release may already be published;
inspect GitHub before retrying. External edits by repository administrators are
outside workflow concurrency protection.

## Failures and retries

For compilation, dependency, binary validation or upstream test failures, inspect
the failed matrix job and its `reports-*` artifact. Test skips are recorded separately
from failures. Retry transient package/network/runner failures by rerunning failed
jobs; dispatch again for a complete fresh build. A successful build of an already
published revision will deliberately fail at publishing rather than replacing it.

If publishing left a draft, inspect its notes and assets. An administrator may delete
the failed draft and, if present, its distribution tag after confirming it was never
published, then rerun the failed publishing job while artifacts remain available
(seven days). Do not delete a published release just to retry. A naming collision
requires choosing a different upstream tag or reviewing the naming policy in code.

## Licensing and runtime

The executables are independently built from unmodified upstream source. Consult
[upstream COPYING](https://github.com/containers/bubblewrap/blob/main/COPYING)
and source-file notices for LGPL-2.0-or-later obligations. Release notes link to the
exact source commit. Binary distributors must retain appropriate notices and meet
applicable source availability obligations; linking a commit alone is not a blanket
claim of compliance. Runtime library dependencies have their own licenses.

See [runtime compatibility and dependency packages](builds.md) for glibc versus musl,
libcap/SELinux, CPU baselines, and user namespace limitations. Bubblewrap also needs
host policy to allow the requested namespace and mount operations; SELinux,
AppArmor, seccomp, or a container runtime can deny them. No setuid mode is enabled.

## Implementation validation

Local validation passed: 13 resolver/publisher unit tests, actionlint, YAML parsing,
explicit dependency/permission/concurrency assertions, and Git whitespace checks.
Publisher fixtures exercise missing/extra files, corrupt checksums, wrong ELF
architecture, source SHA mismatches, existing releases/tags, upload failure, corrupt
remote downloads, and successful draft publication through mocked GitHub calls.
ELF fixtures use a local executable with architecture headers adjusted for validation;
they do not demonstrate working ARM binaries.

No real workflow or release was created: GitHub CLI had no authenticated account
in this environment. Actual GitHub token permissions, draft visibility/downloads,
release/tag creation, concurrency scheduling and all ten native builds still need
an end-to-end Actions run after deployment. The Task 1 Docker limitation also remains.
