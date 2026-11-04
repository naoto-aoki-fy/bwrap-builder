"""Build configuration contracts; requires PyYAML (see docs/builds.md)."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).parents[1]


class BuildConfigTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load((ROOT / '.github/workflows/build.yml').read_text())

    def test_native_matrix_and_publication_gate(self):
        jobs = self.workflow['jobs']
        build = jobs['build']
        rows = build['strategy']['matrix']['include']
        images = {'rocky9': 'rockylinux/rockylinux:9',
                  'rocky10': 'rockylinux/rockylinux:10',
                  'ubuntu24.04': 'ubuntu:24.04', 'ubuntu26.04': 'ubuntu:26.04',
                  'debian13': 'debian:13', 'debian12': 'debian:12',
                  'debian11': 'debian:11', 'alpine': 'alpine:3.24.3'}
        expected = {(d, a) for d in images for a in ('x86_64', 'aarch64')}
        self.assertEqual(len(rows), 16)
        self.assertEqual({(r['distro'], r['arch']) for r in rows}, expected)
        for row in rows:
            self.assertEqual(row['image'], images[row['distro']])
            self.assertEqual(row['runner'], 'ubuntu-24.04' + ('-arm' if row['arch'] == 'aarch64' else ''))
        self.assertEqual(build['runs-on'], '${{ matrix.runner }}')
        self.assertFalse(build['strategy']['fail-fast'])
        self.assertNotIn('continue-on-error', build)
        for step in build['steps']:
            self.assertNotIn('continue-on-error', step)
        self.assertEqual(jobs['publish']['concurrency'],
                         {'group': 'publish-release', 'cancel-in-progress': False})
        self.assertNotIn('release_tag', jobs['resolve']['outputs'])
        self.assertEqual(jobs['publish']['needs'], ['resolve', 'build'])
        self.assertEqual(jobs['publish']['if'], '${{ success() }}')
        spec = importlib.util.spec_from_file_location('publish_config', ROOT / 'scripts/publish.py')
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        self.assertEqual(set(publisher.TARGETS), {f'bwrap-{d}-{a}' for d, a in expected})

    def test_rocky_install_command_and_failure_propagation(self):
        packages = set('gcc meson ninja-build pkgconf-pkg-config libcap-devel libselinux-devel python3 bash file binutils util-linux'.split())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            stub = path / 'dnf'
            stub.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                            'with open(os.environ["COMMAND_LOG"], "a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                            'sys.exit(int(os.environ.get("DNF_EXIT", "0")))\n')
            stub.chmod(0o755)
            log = path / 'commands'
            env = dict(os.environ, PATH=directory + os.pathsep + os.environ['PATH'], COMMAND_LOG=str(log))
            for distro in ('rocky9', 'rocky10'):
                with self.subTest(distro=distro):
                    log.write_text('')
                    subprocess.run(['sh', str(ROOT / 'scripts/install-deps.sh'), distro], env=env, check=True)
                    install, clean = [json.loads(line) for line in log.read_text().splitlines()]
                    self.assertEqual(install[:3], ['-y', '--enablerepo=crb', 'install'])
                    self.assertEqual(set(install[3:]), packages)
                    self.assertEqual(clean, ['clean', 'all'])
                    log.write_text('')
                    result = subprocess.run(['sh', str(ROOT / 'scripts/install-deps.sh'), distro], env=dict(env, DNF_EXIT='42'))
                    self.assertEqual(result.returncode, 42)
                    self.assertEqual(len(log.read_text().splitlines()), 1)

    def test_dockerfile_has_valid_default_base(self):
        lines = (ROOT / 'scripts/Dockerfile').read_text().splitlines()
        self.assertEqual(lines[:2], ['ARG BASE_IMAGE=rockylinux/rockylinux:9', 'FROM ${BASE_IMAGE}'])
