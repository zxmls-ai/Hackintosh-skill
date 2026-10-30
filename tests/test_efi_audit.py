import copy
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'macos-remote-install/scripts'))
import efi_audit as ea


class EfiAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.efi = self.root / 'EFI'
        for p in ea.CORE:
            target = self.efi / p; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'not-a-version: 1.0.0\x00' + p.encode())
        self.config = {'Kernel': {'Add': [
            {'BundlePath': 'Disabled.kext', 'Enabled': False, 'Arch': 'Any',
             'PlistPath': 'Contents/Info.plist', 'ExecutablePath': ''},
            {'BundlePath': 'Limited.kext', 'Enabled': True, 'Arch': 'x86_64',
             'MinKernel': '23.0.0', 'MaxKernel': '23.99.99',
             'PlistPath': 'Contents/Info.plist', 'ExecutablePath': ''}]},
            'UEFI': {'Drivers': [{'Path': 'OpenRuntime.efi', 'Enabled': True}]},
            'Misc': {'Boot': {'PickerMode': 'Builtin'}},
            'PlatformInfo': {'Generic': {'SystemSerialNumber': 'PRIVATE-SERIAL'}}}
        for name in ('Disabled.kext', 'Limited.kext'):
            p = self.efi / 'OC/Kexts' / name / 'Contents/Info.plist'; p.parent.mkdir(parents=True)
            p.write_bytes(plistlib.dumps({'CFBundleVersion': '1.2.3'}))
        self.save()

    def save(self):
        (self.efi / 'OC/config.plist').write_bytes(plistlib.dumps(self.config))

    def test_disabled_is_not_enabled_or_loaded(self):
        row = ea.audit(self.efi)['current']['entries'][0]
        self.assertEqual(row['status'], 'disabled')
        self.assertTrue(row['references'][0]['present'])
        self.assertEqual(row['runtime_loaded'], 'unknown')

    def test_kernel_limits_remain_conditional(self):
        row = ea.audit(self.efi)['current']['entries'][1]
        self.assertEqual(row['status'], 'enabled-conditional')
        self.assertEqual(row['conditions']['MaxKernel'], '23.99.99')

    def test_incidental_binary_string_does_not_become_version(self):
        result = ea.audit(self.efi)
        self.assertEqual(result['current']['oc_version'], 'not-inferred')
        self.assertFalse(result['current']['boot_verified'])

    def test_release_match_requires_all_three_files(self):
        ref = self.root / 'reference'; shutil.copytree(self.efi, ref)
        self.assertTrue(ea.audit(self.efi, oc_reference=ref)['oc_reference']['all_three_match'])
        (ref / ea.CORE[2]).write_bytes(b'wrong-version')
        self.assertFalse(ea.audit(self.efi, oc_reference=ref)['oc_reference']['all_three_match'])
        (ref / ea.CORE[2]).unlink()
        self.assertFalse(ea.audit(self.efi, oc_reference=ref)['oc_reference']['all_three_match'])

    def test_readback_detects_content_and_extra_files(self):
        base = self.root / 'base'; shutil.copytree(self.efi, base)
        (self.efi / ea.CORE[1]).write_bytes(b'different')
        (self.efi / 'OC/old.aml').write_bytes(b'residue')
        diff = ea.audit(self.efi, base)['comparison']
        self.assertFalse(diff['files_identical'])
        self.assertIn('OC/OpenCore.efi', diff['changed_files'])
        self.assertIn('OC/old.aml', diff['added_files'])

    def test_identity_change_detected_without_disclosing_value(self):
        base = self.root / 'base'; shutil.copytree(self.efi, base)
        self.config['PlatformInfo']['Generic']['SystemSerialNumber'] = 'SECOND-SECRET'; self.save()
        report = ea.audit(self.efi, base)
        self.assertIn('/PlatformInfo/Generic/SystemSerialNumber', report['comparison']['config_change_paths'])
        self.assertNotIn('PRIVATE-SERIAL', json.dumps(report))
        self.assertNotIn('SECOND-SECRET', json.dumps(report))

    def test_comments_not_semantic_but_bytes_still_differ(self):
        base = self.root / 'base'; shutil.copytree(self.efi, base)
        self.config['Kernel']['Add'][0]['Comment'] = 'private note'; self.save()
        diff = ea.audit(self.efi, base)['comparison']
        self.assertFalse(diff['files_identical']); self.assertEqual(diff['config_change_paths'], [])

    def test_list_order_and_flag_changes_are_retained(self):
        before = copy.deepcopy(self.config)
        self.config['Kernel']['Add'].reverse()
        paths = ea.changes(before, self.config)
        self.assertIn('/Kernel/Add/0/Enabled', paths)

    def test_path_traversal_rejected_even_for_disabled_item(self):
        self.config['Kernel']['Add'][0]['BundlePath'] = '../outside.kext'; self.save()
        with self.assertRaises(ValueError): ea.audit(self.efi)

    def test_missing_reference_not_treated_as_present(self):
        (self.efi / 'OC/Kexts/Limited.kext/Contents/Info.plist').unlink()
        row = ea.audit(self.efi)['current']['entries'][1]
        self.assertFalse(row['references'][0]['present'])

    def test_changed_snapshot_refused(self):
        original = ea.snapshot; calls = [0]
        def changing(root):
            result = original(root); calls[0] += 1
            if calls[0] == 2: result.pop('OC/OpenCore.efi')
            return result
        with patch.object(ea, 'snapshot', changing):
            with self.assertRaises(ValueError): ea.audit(self.efi)

    def test_cli_refuses_overwrite_and_output_inside_source(self):
        script = Path(ea.__file__)
        for output in (self.efi / 'report.json', self.root / 'exists.json'):
            if output.parent == self.root: output.write_text('keep')
            p = subprocess.run([sys.executable, '-B', str(script), '--efi', str(self.efi), '--out', str(output)], capture_output=True)
            self.assertEqual(p.returncode, 2)
        self.assertEqual((self.root / 'exists.json').read_text(), 'keep')

    def test_cli_writes_report_without_changing_efi(self):
        before = ea.snapshot(self.efi); out = self.root / 'report.json'
        p = subprocess.run([sys.executable, '-B', str(Path(ea.__file__)), '--efi', str(self.efi), '--out', str(out)], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(out.read_text())['schema'], 'efi-audit-v1')
        self.assertEqual(ea.snapshot(self.efi), before)


if __name__ == '__main__': unittest.main()
