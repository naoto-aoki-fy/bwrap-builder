import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('resolver', Path(__file__).parents[1] / 'scripts/resolve.py')
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('commit', '--allow-empty', '-qm', 'initial')
        self.sha = self.git('rev-parse', 'HEAD')
        self.git('tag', 'v-test')
        self.git('tag', '-a', 'v-annotated', '-m', 'annotated')
        self.git('branch', 'branch-only')

    def git(self, *args):
        return resolver.git(self.repo, *args)

    def test_exact_tags_and_annotated_tag_peeling(self):
        for ref in ['v-test', 'v-annotated']:
            self.assertEqual(resolver.resolve(self.repo, ref), self.sha)

    def test_full_and_abbreviated_commit(self):
        for ref in [self.sha, self.sha[:8], self.sha[:8].upper()]:
            self.assertEqual(resolver.resolve(self.repo, ref), self.sha)

    def test_hexadecimal_tag_has_precedence(self):
        self.git('tag', 'deadbeef')
        self.assertEqual(resolver.resolve(self.repo, 'deadbeef'), self.sha)

    def test_invalid_and_injection_inputs(self):
        for ref in ['branch-only', 'HEAD', 'v-test^{}', '--help', '$(touch /tmp/injected)', '', 'v-test\n', 'abc', '0' * 40]:
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                resolver.resolve(self.repo, ref)

    def test_noncommit_object(self):
        tree = self.git('rev-parse', 'HEAD^{tree}')
        with self.assertRaises(ValueError):
            resolver.resolve(self.repo, tree)

    def test_ambiguous_hash_is_rejected(self):
        with patch.object(resolver, 'git', side_effect=['', 'a' * 40 + '\n' + 'b' * 40]):
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                resolver.resolve(self.repo, 'abcd')


if __name__ == '__main__':
    unittest.main()
