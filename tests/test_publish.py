import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).parents[1] / 'scripts/publish.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifacts = self.root / 'artifacts'
        self.reports = self.root / 'reports'
        self.sha = 'a' * 40
        for name, arch in p.TARGETS.items():
            directory = self.artifacts / name
            directory.mkdir(parents=True)
            binary = bytearray(Path('/bin/true').read_bytes())
            binary[18:20] = (62 if arch == 'x86_64' else 183).to_bytes(2, 'little')
            (directory / name).write_bytes(binary)
            report = self.reports / name.replace('bwrap-', 'reports-', 1)
            report.mkdir(parents=True)
            (report / 'sha256.txt').write_text(hashlib.sha256(binary).hexdigest() + '  ' + name + '\n')
            (report / 'upstream-sha.txt').write_text(self.sha + '\n')
            (report / 'ldd.txt').write_text('libc\n')

    def collect(self):
        return p.collect(self.artifacts, self.reports, self.sha)

    def test_next_release_tag(self):
        self.assertEqual(p.next_release_tag([]), 'v0.0.1')
        self.assertEqual(p.next_release_tag(['bwrap-v9.9.9', 'v01.2.3', 'v1.2.3-rc.1',
                                           'v1.2.3+build', '1.2.3', 'v1.2', 'v1.2.3\n']), 'v0.0.1')
        self.assertEqual(p.next_release_tag(['v1.9.99', 'v1.10.9', 'v1.10.10']), 'v1.10.11')
        self.assertEqual(p.next_release_tag(['v2.0.0', 'v1.999.999']), 'v2.0.1')

    def test_current_commit_tag_takes_precedence(self):
        tags = [{'name': name, 'commit': {'sha': sha}} for name, sha in
                [('v9.0.0', 'other'), ('v1.2.9', 'current'),
                 ('v1.2.10', 'current'), ('v99.0.0-rc.1', 'current')]]
        self.assertEqual(p.select_release_tag(tags, 'current'), 'v1.2.10')
        self.assertEqual(p.select_release_tag(tags, 'untagged'), 'v9.0.1')

    def test_complete_set(self):
        files, sums = self.collect()
        self.assertEqual(len(files), 16)
        self.assertEqual(set(sums), set(p.TARGETS))

    def test_missing_extra_duplicate_and_archive(self):
        name = next(iter(p.TARGETS))
        path = self.artifacts / name / name
        for extra in ['duplicate', 'unexpected.zip']:
            other = path.with_name(extra)
            other.write_text('extra')
            with self.assertRaises(ValueError):
                self.collect()
            other.unlink()
        path.unlink()
        with self.assertRaises(ValueError):
            self.collect()

    def test_checksum_architecture_and_source_mismatch(self):
        name = next(iter(p.TARGETS))
        path = self.artifacts / name / name
        original = path.read_bytes()
        path.write_bytes(original + b'corruption')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.collect()
        path.write_bytes(original[:18] + b'\x00\x00' + original[20:])
        with self.assertRaisesRegex(ValueError, 'ELF'):
            self.collect()
        path.write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'Upstream SHA'):
            p.collect(self.artifacts, self.reports, 'b' * 40)

    def test_existing_release_and_tag_fail_without_mutation(self):
        old = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        env = dict(UPSTREAM_SHA=self.sha, GITHUB_REPOSITORY='owner/repo', GITHUB_SHA='b' * 40)
        with patch.dict(os.environ, env), patch.object(p, 'gh', side_effect=['[[]]', '[[{"tag_name":"v0.0.1"}]]']), patch.object(p, 'api') as api:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                p.main()
            api.assert_not_called()
        with patch.dict(os.environ, env), patch.object(p, 'gh', return_value='[[]]'), patch.object(p, 'api', side_effect=[[{'ref': 'refs/tags/v0.0.1'}], {'sha': 'c' * 40}]) as api:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                p.main()
            self.assertEqual(api.call_count, 2)

    def test_upload_failure_never_publishes(self):
        old = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        env = dict(UPSTREAM_SHA=self.sha, GITHUB_REPOSITORY='owner/repo',
                   GITHUB_SERVER_URL='https://github.com', GITHUB_RUN_ID='1', GITHUB_SHA='b'*40, UPSTREAM_REF='v-test')
        with patch.dict(os.environ, env), patch.object(p, 'gh', side_effect=['[[]]', '[[]]', RuntimeError('upload failed')]), patch.object(p, 'api', side_effect=[[], {'id': 1}]) as api:
            with self.assertRaisesRegex(RuntimeError, 'upload failed'):
                p.main()
            self.assertEqual(api.call_count, 2)
            self.assertFalse(any(c.kwargs.get('method') == 'PATCH' for c in api.call_args_list))

    def test_remote_verification_gates_publication(self):
        old = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        env = dict(UPSTREAM_SHA=self.sha, GITHUB_REPOSITORY='owner/repo',
                   GITHUB_SERVER_URL='https://github.com', GITHUB_RUN_ID='1', GITHUB_SHA='b'*40,
                   UPSTREAM_REF='v-test', GITHUB_STEP_SUMMARY=str(self.root / 'summary'))
        assets = [{'name': n, 'state': 'uploaded'} for n in p.TARGETS]
        for corrupt in [True, False]:
            def fake_gh(*args, **kwargs):
                if args[0] == 'api':
                    if args[-1].endswith('/tags?per_page=100'):
                        self.assertEqual(args[1:4], ('--paginate', '--slurp', 'repos/owner/repo/tags?per_page=100'))
                        return '[[{"name":"v1.2.9","commit":{"sha":"other"}}], [{"name":"v1.2.10","commit":{"sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}]]'
                    return '[[]]'
                if args[:2] == ('release', 'download'):
                    directory = Path(args[args.index('--dir') + 1])
                    for n in p.TARGETS:
                        shutil.copyfile(self.artifacts / n / n, directory / n)
                    if corrupt:
                        (directory / next(iter(p.TARGETS))).write_bytes(b'bad upload')
                return ''
            responses = [[{'ref': 'refs/tags/v1.2.10'}], {'sha': 'b' * 40}, {'id': 1}, assets]
            if not corrupt:
                responses.append({'draft': False, 'html_url': 'https://example.invalid/release'})
            with patch.dict(os.environ, env), patch.object(p, 'gh', side_effect=fake_gh), patch.object(p, 'api', side_effect=responses) as api:
                if corrupt:
                    with self.assertRaises(ValueError):
                        p.main()
                    self.assertFalse(any(c.kwargs.get('method') == 'PATCH' for c in api.call_args_list))
                else:
                    p.main()
                    creation = api.call_args_list[2].kwargs['data']
                    self.assertEqual(creation['tag_name'], 'v1.2.10')
                    self.assertEqual(creation['target_commitish'], 'b' * 40)
                    self.assertEqual(api.call_args.kwargs['data']['draft'], False)
                    self.assertEqual(api.call_args.kwargs['method'], 'PATCH')
