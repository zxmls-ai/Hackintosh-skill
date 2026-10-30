from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'macos-remote-install/scripts'
sys.path.insert(0, str(SCRIPTS))
import prepare_ssh_handoff as handoff


class PrepareHandoffTests(unittest.TestCase):
    def setUp(self):
        self.source = handoff.SOURCE.read_text(encoding='utf-8-sig')

    def test_only_ip_line_changes_and_duplicate_addresses_are_removed(self):
        rendered = handoff.render(self.source, ['198.51.100.2', '203.0.113.2', '198.51.100.2'])
        before, after = self.source.splitlines(), rendered.splitlines()
        differences = [(a, b) for a, b in zip(before, after) if a != b]
        self.assertEqual(len(before), len(after))
        self.assertEqual(len(differences), 1)
        self.assertEqual(differences[0][1], "    $BIPv4 = @('198.51.100.2', '203.0.113.2')")

    def test_unavailable_b_ip_keeps_empty_array(self):
        self.assertIn('    $BIPv4 = @()\n', handoff.render(self.source, []))

    def test_invalid_address_and_injection_fail_before_rendering(self):
        for address in ["198.51.100.2'); Start-Service sshd #", '::1', '999.1.1.1', 'unknown']:
            with self.subTest(address=address), self.assertRaises(ValueError):
                handoff.render(self.source, [address])

    def test_missing_or_duplicate_placeholder_is_rejected(self):
        for source in [self.source.replace('$BIPv4 = @()', '$BIPv4 = @(1)'), self.source + '\n    $BIPv4 = @()\n']:
            with self.assertRaises(ValueError):
                handoff.render(source, [])

    def test_cli_delivers_exact_bom_file_and_will_not_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='prepare-ssh-') as directory:
            out = Path(directory) / 'ready.ps1'
            command = [sys.executable, '-B', str(SCRIPTS / 'prepare_ssh_handoff.py'), '--b-ip', '198.51.100.2', '--out', str(out)]
            result = subprocess.run(command, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = handoff.render(self.source, ['198.51.100.2']).encode('utf-8-sig')
            self.assertEqual(out.read_bytes(), expected)
            again = subprocess.run(command, capture_output=True, timeout=15)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(out.read_bytes(), expected)
