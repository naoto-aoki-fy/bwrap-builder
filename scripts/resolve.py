#!/usr/bin/env python3
"""Resolve exact tags or unique hexadecimal commit prefixes; export pristine source."""
import os
import re
import subprocess
import sys
from pathlib import Path

UPSTREAM = 'https://github.com/containers/bubblewrap.git'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def resolve(repo, ref):
    # Tags take precedence, even if their names happen to be hexadecimal.
    tags = git(repo, 'for-each-ref', '--format=%(refname)', 'refs/tags').splitlines()
    if 'refs/tags/' + ref in tags:
        return git(repo, 'rev-parse', '--verify', 'refs/tags/' + ref + '^{commit}')
    if not re.fullmatch(r'[0-9a-fA-F]{4,40}', ref):
        raise ValueError('Expected an exact upstream tag or a 4–40 digit hexadecimal commit hash; branches are not accepted')
    objects = git(repo, 'rev-parse', '--disambiguate=' + ref.lower()).splitlines()
    if len(objects) != 1 or git(repo, 'cat-file', '-t', objects[0]) != 'commit':
        raise ValueError('Commit hash is missing, ambiguous, or does not identify a commit')
    return objects[0]


def main():
    ref = os.environ['UPSTREAM_REF']
    repo = Path('upstream.git')
    # Full history is necessary to prove uniqueness of abbreviated hashes.
    subprocess.run(['git', 'clone', '--mirror', UPSTREAM, str(repo)], check=True)
    sha = resolve(repo, ref)
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Upstream did not resolve to a SHA-1 commit')
    subprocess.run(['git', '-C', str(repo), 'archive', '--format=tar',
                    '--output=' + str(Path('source.tar').resolve()), sha], check=True)
    Path('resolved-sha.txt').write_text(sha + '\n')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('sha=' + sha + '\n')
    print('Resolved upstream commit: ' + sha)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as exc:
        print('Revision resolution failed: ' + str(exc), file=sys.stderr)
        sys.exit(1)
