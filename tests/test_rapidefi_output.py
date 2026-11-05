import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHELL = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'


@unittest.skipUnless(SHELL.is_file(), 'Windows PowerShell is required')
class RapidEFIOutputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.desktop = Path(temp.name) / 'Redirected Desktop 测试'
        self.desktop.mkdir()

    def make_candidate(self, name, boot=True):
        parent = self.desktop / name
        config = parent / 'EFI/OC/config.plist'
        config.parent.mkdir(parents=True)
        config.write_bytes(b'fixture plist; discover only, not validate')
        if boot:
            loader = parent / 'EFI/BOOT/BOOTx64.efi'
            loader.parent.mkdir()
            loader.write_bytes(b'fixture loader')
        (parent / 'configModel.json').write_text('{}', encoding='utf-8')
        return config

    def invoke(self, *extra):
        result = subprocess.run([str(SHELL), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(ROOT / 'macos-remote-install/scripts/find-rapidefi-output.ps1'),
            '-DesktopPath', str(self.desktop), *extra], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        return json.loads(result.stdout.decode('utf-8-sig'))

    def test_real_output_is_found_beneath_the_supplied_desktop(self):
        config = self.make_candidate('RapidEFI generated')
        self.make_candidate('incomplete', boot=False)
        output = self.invoke()
        self.assertEqual(output['DesktopRoots'], [str(self.desktop)])
        self.assertEqual(len(output['Candidates']), 1)
        item = output['Candidates'][0]
        self.assertEqual(item['Config'], str(config))
        self.assertEqual(len(item['ConfigModel']), 1)
        self.assertTrue(item['NewSinceStart'])

    def test_multiple_old_candidates_are_reported_without_claiming_new_generation(self):
        self.make_candidate('one')
        self.make_candidate('two')
        output = self.invoke('-StartedAfter', '2099-01-01T00:00:00Z')
        self.assertEqual(len(output['Candidates']), 2)
        self.assertTrue(all(not item['NewSinceStart'] for item in output['Candidates']))
        self.assertNotIn('Selected', output)


if __name__ == '__main__':
    unittest.main()
