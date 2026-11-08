"""Package-check CLI contracts on disposable packages without Git history."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PACKAGE = Path(__file__).resolve().parents[1]


class PackageCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / 'agentic-workflow'
        shutil.copytree(PACKAGE, self.package,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(self.package / 'helpers/check_package.py'), *arguments],
            cwd=self.root, capture_output=True, text=True)

    def result(self, process, code):
        self.assertEqual(process.returncode, code, process.stdout + process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report['status'], 'PASS' if code == 0 else 'FAIL')
        self.assertGreater(report['local_links_checked'], 0)
        return report

    def test_valid_package_ignores_host_instructions(self):
        (self.root / 'AGENTS.md').write_text('[Host-only reference](absent.md)\n')
        self.assertEqual(self.result(self.cli(), 0)['errors'], [])

    def test_additional_valid_markdown_is_allowed_and_checked(self):
        (self.package / 'extra.md').write_text(
            '# Extra\n[Routing](policies/MODELS.md#model-routing)\n')
        self.assertEqual(self.result(self.cli(), 0)['errors'], [])

    def test_broken_local_link_and_anchor_fail(self):
        extra = self.package / 'extra.md'
        for target in ('missing.md', 'AGENTS.md#absent-heading'):
            with self.subTest(target=target):
                extra.write_text(f'# Extra\n[Reference]({target})\n')
                report = self.result(self.cli(), 1)
                self.assertTrue(any(target in error for error in report['errors']))

    def test_missing_required_role_and_template_fail(self):
        for relative in ('roles/REVIEWER.md', 'templates/verification.md', 'helpers/records.py'):
            with self.subTest(path=relative):
                path = self.package / relative
                original = path.read_bytes()
                path.unlink()
                try:
                    report = self.result(self.cli(), 1)
                    self.assertIn(f'Missing package file: {relative}', report['errors'])
                finally:
                    path.write_bytes(original)

    def test_link_outside_package_fails_even_when_host_file_exists(self):
        (self.root / 'host.md').write_text('# Host dependency\n')
        (self.package / 'extra.md').write_text('[Host](../host.md)\n')
        report = self.result(self.cli(), 1)
        self.assertTrue(any('outside copy boundary' in error for error in report['errors']))

    def test_unreadable_document_returns_inability_to_run(self):
        (self.package / 'extra.md').write_bytes(b'\xff')
        process = self.cli()
        self.assertEqual(process.returncode, 2)
        self.assertIn('Package check could not complete:', process.stderr)


if __name__ == '__main__':
    unittest.main()
