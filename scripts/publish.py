#!/usr/bin/env python3
"""Validate all build artifacts before creating and publishing a complete draft."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote

TARGETS = {f'bwrap-{d}-{a}': a for d in
           ('rocky9', 'rocky10', 'ubuntu24.04', 'ubuntu26.04', 'alpine')
           for a in ('x86_64', 'aarch64')}


def validate_binary(path, arch, checksum):
    if path.is_symlink() or not path.is_file() or not path.stat().st_size:
        raise ValueError(f'Missing or invalid executable: {path}')
    header = path.read_bytes()[:64]
    # ELF64, little endian, current ELF version, EXEC or PIE, native machine.
    machine = 62 if arch == 'x86_64' else 183
    if (len(header) < 64 or header[:7] != b'\x7fELF\x02\x01\x01'
            or int.from_bytes(header[16:18], 'little') not in (2, 3)
            or int.from_bytes(header[18:20], 'little') != machine):
        raise ValueError(f'Invalid ELF architecture/type: {path}')
    subprocess.run(['readelf', '-h', '-l', str(path)], check=True, stdout=subprocess.DEVNULL)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != checksum:
        raise ValueError(f'SHA-256 mismatch: {path}')


def collect(root, reports, sha):
    if {p.name for p in root.iterdir()} != set(TARGETS):
        raise ValueError('Expected exactly ten distinct executable artifact directories')
    files, checksums = [], {}
    for name, arch in sorted(TARGETS.items()):
        directory = root / name
        if directory.is_symlink() or not directory.is_dir() or [p.name for p in directory.iterdir()] != [name]:
            raise ValueError(f'Unexpected/duplicated files in artifact {name}')
        report = reports / name.replace('bwrap-', 'reports-', 1)
        if (report / 'upstream-sha.txt').read_text().strip() != sha:
            raise ValueError(f'Upstream SHA mismatch: {name}')
        match = re.fullmatch(r'([0-9a-f]{64})  ' + re.escape(name) + r'\n?',
                             (report / 'sha256.txt').read_text())
        if not match:
            raise ValueError(f'Invalid checksum manifest: {name}')
        checksums[name] = match[1]
        path = directory / name
        validate_binary(path, arch, match[1])
        files.append(path)
    return files, checksums


def gh(*args, data=None):
    return subprocess.check_output(['gh', *args], text=True,
                                   input=json.dumps(data) if data is not None else None)


def api(endpoint, data=None, method=None):
    args = ['api', endpoint]
    if method:
        args += ['--method', method]
    if data is not None:
        args += ['--input', '-']
    return json.loads(gh(*args, data=data))


def main():
    sha, tag = os.environ['UPSTREAM_SHA'], os.environ['RELEASE_TAG']
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Invalid resolved SHA')
    subprocess.run(['git', 'check-ref-format', 'refs/tags/' + tag], check=True)
    files, sums = collect(Path('artifacts'), Path('reports'), sha)
    repo = os.environ['GITHUB_REPOSITORY']
    base = f'repos/{repo}'
    # Listing errors fail closed; do not treat authentication/network errors as absence.
    pages = json.loads(gh('api', '--paginate', '--slurp', base + '/releases?per_page=100'))
    if any(r['tag_name'] == tag for page in pages for r in page):
        raise ValueError(f'Release {tag} already exists (published or draft); refusing to overwrite')
    refs = api(base + '/git/matching-refs/tags/' + quote(tag, safe=''))
    if any(r['ref'] == 'refs/tags/' + tag for r in refs):
        raise ValueError(f'Distribution tag {tag} already exists; refusing to reuse it')
    run = f"{os.environ['GITHUB_SERVER_URL']}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    notes = f'''Independently built binaries; these are not official upstream release assets.

Upstream project: https://github.com/containers/bubblewrap
Original upstream identifier: {os.environ['UPSTREAM_REF']}
Full upstream commit: {sha}
Exact source: https://github.com/containers/bubblewrap/tree/{sha}
Build run: {run}

Targets: Rocky Linux 9 and 10, Ubuntu 24.04 and 26.04, Alpine Linux 3.24.3;
each for x86_64 and aarch64. Files are raw ELF executables.

Built with Meson/Ninja in native distribution containers, libcap enabled,
SELinux enabled on Rocky/Ubuntu and disabled on Alpine. Tests enabled, man pages
disabled, upstream completion defaults, no setuid installation, no assumed kernel
version or custom source patches. Dynamically linked: use the target distribution's
libc (glibc on Rocky/Ubuntu, musl on Alpine), libcap, and libselinux on Rocky/Ubuntu.
Rocky Linux 10 CPU baselines apply. User namespaces must be enabled and permitted
by the host kernel, LSM and container policy. Help/version checks do not prove
sandbox creation is permitted. See the workflow reports for test passes/skips.
Distribution tags identify this builder repository, not upstream source history.

SHA-256 checksums:

```
'''
    notes += ''.join(f'{sums[n]}  {n}\n' for n in sorted(sums)) + '```\n\nRuntime library dependencies recorded by each build:\n'
    for name in sorted(sums):
        report = Path('reports') / name.replace('bwrap-', 'reports-', 1)
        notes += f'\n{name}:\n\n```text\n{(report / "ldd.txt").read_text()}```\n'
    release = api(base + '/releases', data={
        'tag_name': tag, 'target_commitish': os.environ['GITHUB_SHA'],
        'name': tag, 'body': notes, 'draft': True, 'make_latest': 'false'})
    endpoint = base + '/releases/' + str(release['id'])
    print(f'Created draft {tag}; failures leave it unpublished for inspection.', flush=True)
    gh('release', 'upload', tag, *map(str, files), '--repo', repo)
    assets = api(endpoint + '/assets?per_page=100')
    if (len(assets) != 10 or {a['name'] for a in assets} != set(TARGETS)
            or any(a['state'] != 'uploaded' for a in assets)):
        raise ValueError('Draft assets are incomplete, duplicated, or unexpected')
    with tempfile.TemporaryDirectory() as temp:
        gh('release', 'download', tag, '--repo', repo, '--dir', temp)
        if {p.name for p in Path(temp).iterdir()} != set(TARGETS):
            raise ValueError('Downloaded draft does not contain exactly ten executables')
        for name, arch in TARGETS.items():
            validate_binary(Path(temp) / name, arch, sums[name])
    published = api(endpoint, method='PATCH', data={'draft': False, 'make_latest': 'false'})
    if published['draft']:
        raise ValueError('GitHub did not publish the verified draft')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write(f"Published [{tag}]({published['html_url']}) with ten verified ELF assets.\n")
    print(published['html_url'])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Publishing failed: {exc}. Any created draft remains unpublished; inspect it before retrying.', file=sys.stderr)
        sys.exit(1)
