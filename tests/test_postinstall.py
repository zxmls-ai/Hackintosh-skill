import copy
import json
from pathlib import Path
import plistlib
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'macos-remote-install/scripts'))
import workflow as flow
import postinstall_guard as guard
from ssh_transport import Fault

MACHINE = {'uuid': '00000000-0000-4000-8000-000000000001'}
ESP = '00000000-0000-4000-8000-000000000002'


def put(run, path, data):
    p = run / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode('utf-8'))
    return p


def device_fixture(run, machine):
    """Synthetic functional evidence only; never a report of real machine tests."""
    put(run, 'evidence/fixture.txt', b'SYNTHETIC independent observation fixture')
    put(run, 'evidence/tested.plist', plistlib.dumps({'Misc': {'Boot': {'ShowPicker': True, 'Timeout': 10}}, 'Kernel': {'Add': []}}))
    devs = [dict(PNPDeviceID='PCI\\NIC_A', PNPClass='Net'),
            dict(PNPDeviceID='PCI\\NIC_B', PNPClass='Net'),
            dict(PNPDeviceID='PCI\\GPU_A', PNPClass='Display')]
    put(run, 'inventory/windows.json', {'platform': 'windows', 'host': machine, 'pnp': devs, 'gpus': []})
    data = {'schema': 'device-audit-v1', 'machine_uuid': machine['uuid'], 'macos_build': 'synthetic-build',
            'windows_inventory': 'inventory/windows.json', 'tested_config': 'evidence/tested.plist'}
    for key in ('macos_inventory', 'coverage_review', 'presented', 'rollback', 'tested_efi_manifest'):
        data[key] = 'evidence/fixture.txt'
    data['items'] = []
    for kind in guard.CATEGORIES[:-1]:
        for number in range(2 if kind == 'network' else 1):
            pnp = (['PCI\\NIC_A', 'PCI\\NIC_B'][number] if kind == 'network' else
                   'PCI\\GPU_A' if kind == 'gpu' else None)
            data['items'].append({'id': kind + str(number), 'category': kind, 'name': kind + ' fixture',
                'hardware_id': pnp or kind, 'windows_ids': [pnp] if pnp else [],
                'observed': 'Synthetic test result', 'driver_state': 'fixture', 'status': 'passed',
                'evidence': ['evidence/fixture.txt'], 'test': {'kind': 'functional', 'basis': 'tool',
                'result': 'Synthetic expected output matched', 'evidence': 'evidence/fixture.txt'}})
    return data


def register_fixture(run, state):
    state.setdefault('machine_a', copy.deepcopy(MACHINE))
    if not state.get('machine_a'): state['machine_a'] = copy.deepcopy(MACHINE)
    data = device_fixture(run, state['machine_a'])
    flow.record_devices(run, state, put(run, 'evidence/devices.json', data))
    return data


class PostInstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run = Path(temp.name) / 'run'
        self.state = flow.initialize(self.run)
        self.state.update(phase='06-devices', step='guided-contract', machine_a=copy.deepcopy(MACHINE))
        self.data = device_fixture(self.run, MACHINE)

    def save_devices(self, data=None, name='devices.json'):
        return put(self.run, 'evidence/' + name, data or self.data)

    def review(self, phase=None):
        phase = phase or self.state['phase']
        report = {'phase': phase, 'checks': {name: {'result': 'pass', 'basis': 'tool',
            'evidence': ['evidence/fixture.txt']} for name in flow.PHASES[phase]['verification']},
            'source_plans': [], 'no_driver_changes': 'Synthetic already-working hardware'}
        return report

    def boot(self):
        return {'schema': 'boot-readiness-v1', 'machine_uuid': MACHINE['uuid'], 'firmware_mode': 'UEFI',
            'esp_guid': ESP, 'backup': 'evidence/fixture.txt', 'authorization': 'evidence/fixture.txt',
            'readback': 'evidence/fixture.txt', 'windows_preserved': 'evidence/fixture.txt',
            'firmware_readback': 'evidence/fixture.txt', 'config': 'evidence/tested.plist',
            'registration_method': 'synthetic global firmware registration',
            'variable_namespace': 'EFI_GLOBAL_VARIABLE', 'entry': {'id': 'Boot0007', 'active': True,
            'esp_guid': ESP, 'path': '\\EFI\\OC\\OpenCore.efi'}, 'boot_order': ['Boot0007', 'Boot0000'], 'boot_next': None}

    def close_devices(self):
        flow.record_devices(self.run, self.state, self.save_devices())
        flow.guided_review(self.run, self.state, put(self.run, 'review06.json', self.review()))

    def test_ssh_success_routes_to_scan_not_esp(self):
        self.state.update(phase='05-macos-remote')
        flow.guided_review(self.run, self.state, put(self.run, 'review05.json', self.review()))
        self.assertEqual(self.state['phase'], '06-devices')
        self.assertEqual(flow.render_result(self.state)['next_action'], 'record-devices')

    def test_cli_records_scan_and_renders_priority_from_persisted_state(self):
        for item in self.data['items'][:3]:
            item.update(status='pending', next_action='synthetic functional test')
        flow.save(self.run, self.state, 'fixture-cli-phase')
        command=[sys.executable, '-B', str(flow.ROOT/'workflow.py'), '--run', str(self.run), '--json']
        env=dict(os.environ, PYTHONIOENCODING='utf-8')
        result=subprocess.run(command+['record-devices','--file',str(self.save_devices())],
                              capture_output=True,encoding='utf-8',env=env,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(json.loads(result.stdout)['device_queue']['next_item'],'network0')
        blocked=subprocess.run(command+['review','--file',str(put(self.run,'review06.json',self.review()))],
                               capture_output=True,encoding='utf-8',env=env,timeout=30)
        self.assertEqual(blocked.returncode,2)
        self.assertEqual(json.loads(blocked.stdout)['error'],'DEVICE_AUDIT_OPEN')
        self.assertEqual(flow.load(self.run)['phase'],'06-devices')

    def test_blanket_all_pass_report_cannot_skip_device_list(self):
        with self.assertRaises(Fault) as err:
            flow.guided_review(self.run, self.state, put(self.run, 'review.json', self.review()))
        self.assertEqual(err.exception.code, 'DEVICE_AUDIT_REQUIRED')
        self.assertEqual(self.state['phase'], '06-devices')

    def test_windows_second_nic_cannot_be_omitted_or_grouped(self):
        for mode in ('missing', 'grouped', 'not-applicable'):
            d = copy.deepcopy(self.data)
            if mode == 'not-applicable':
                d['items'][1].update(status='not-applicable', reason='hidden', applicability='evidence/fixture.txt')
            else:
                d['items'].pop(1)
                if mode == 'grouped': d['items'][0]['windows_ids'].append('PCI\\NIC_B')
            with self.subTest(mode=mode), self.assertRaises(Fault):
                guard.check_devices(self.run, MACHINE, 'evidence/' + self.save_devices(d).name)

    def test_missing_function_category_and_identity_fail(self):
        self.data['items'] = [i for i in self.data['items'] if i['category'] != 'sleep']
        with self.assertRaises(Fault): flow.record_devices(self.run, self.state, self.save_devices())
        self.data = device_fixture(self.run, MACHINE); self.data['machine_uuid'] = 'other'
        with self.assertRaises(Fault): flow.record_devices(self.run, self.state, self.save_devices())

    def test_enumeration_cannot_be_called_passed(self):
        self.data['items'][2]['test']['kind'] = 'inspection'
        with self.assertRaises(Fault): flow.record_devices(self.run, self.state, self.save_devices())

    def test_deferred_gpu_does_not_block_next_usb_but_blocks_esp(self):
        for i in self.data['items']:
            if i['category'] in ('gpu', 'usb'):
                i.update(status='deferred' if i['category'] == 'gpu' else 'pending', next_action='continue verification',
                         research=[{'url': 'https://example.org/maintainer', 'finding': 'synthetic source review', 'evidence': 'evidence/fixture.txt'}])
        flow.record_devices(self.run, self.state, self.save_devices())
        self.assertEqual(flow.render_result(self.state)['device_queue']['next_item'], 'usb0')
        with self.assertRaises(Fault) as err:
            flow.guided_review(self.run, self.state, put(self.run, 'review.json', self.review()))
        self.assertEqual(err.exception.code, 'DEVICE_AUDIT_OPEN')
        with self.assertRaises(Fault): flow.boot_ready(self.run, self.state, put(self.run, 'boot.json', self.boot()))

    def test_network_has_priority_over_gpu_and_waiting_network_can_yield(self):
        for i in self.data['items']:
            i.update(status='pending', next_action='synthetic next test')
        self.assertEqual(guard.device_queue(self.data)['next_item'], 'network0')
        for i in self.data['items'][:2]: i['status'] = 'waiting-user'
        self.assertEqual(guard.device_queue(self.data)['next_item'], 'gpu0')

    def test_real_device_rows_cannot_be_removed_after_registration(self):
        flow.record_devices(self.run, self.state, self.save_devices())
        self.data['items'] = [i for i in self.data['items'] if i['id'] != 'audio0']
        # Keep category with a new identity; must not forget the original row.
        self.data['items'].append({**self.data['items'][-1], 'id': 'replacement', 'category': 'audio'})
        with self.assertRaises(Fault): flow.record_devices(self.run, self.state, self.save_devices(name='devices02.json'))

    def test_deferred_requires_research_and_acceptance_is_not_inferred(self):
        self.data['items'][2].update(status='deferred', next_action='find support')
        with self.assertRaises(Fault): flow.record_devices(self.run, self.state, self.save_devices())
        self.data['items'][2].update(status='accepted-limit', reason='cannot repair')
        with self.assertRaises(Fault): flow.record_devices(self.run, self.state, self.save_devices())
        self.data['items'][2]['acceptance'] = 'evidence/fixture.txt'
        self.close_devices()
        self.assertEqual(self.state['phase'], '07-boot')
        self.assertTrue(self.state['guided_reviews'][-1]['limited'])

    def test_tampering_invalidates_recorded_scan(self):
        flow.record_devices(self.run, self.state, self.save_devices())
        put(self.run, 'evidence/fixture.txt', b'changed')
        with self.assertRaises(Fault) as err: flow.load(self.run)
        self.assertEqual(err.exception.code, 'EVIDENCE_CHANGED')

    def test_copy_only_or_launcher_only_or_wrong_namespace_is_rejected(self):
        self.close_devices()
        for field, value in [('entry', {}), ('boot_order', ['Boot0000','Boot0007']),
                             ('boot_next', 'Boot0000'), ('variable_namespace', 'OPENCORE_VENDOR_VARIABLE')]:
            d = self.boot(); d[field] = value
            with self.subTest(field=field), self.assertRaises(Fault):
                flow.boot_ready(self.run, self.state, put(self.run, 'boot.json', d))

    def test_wrong_esp_or_hidden_menu_or_hardware_drift_is_rejected(self):
        self.close_devices()
        d = self.boot(); d['entry']['esp_guid'] = '00000000-0000-4000-8000-000000000099'
        with self.assertRaises(Fault): flow.boot_ready(self.run,self.state,put(self.run,'boot.json',d))
        for change in ('hidden', 'timeout', 'hardware'):
            d=self.boot(); c=plistlib.loads((self.run/d['config']).read_bytes())
            if change=='hidden': c['Misc']['Boot']['ShowPicker']=False
            elif change=='timeout': c['Misc']['Boot']['Timeout']=0
            else: c['Kernel']['Add'].append({'BundlePath':'unverified.kext'})
            d['config']='evidence/readback.plist'; put(self.run,d['config'],plistlib.dumps(c))
            with self.subTest(change=change), self.assertRaises(Fault):
                flow.boot_ready(self.run,self.state,put(self.run,'boot.json',d))

    def test_preflight_does_not_mean_cold_boot_passed(self):
        self.close_devices(); d=self.boot()
        flow.boot_ready(self.run,self.state,put(self.run,'boot-before.json',d))
        self.assertEqual(flow.render_result(self.state)['next_action'],'cold-boot-then-review')
        report=self.review(); report['boot_manifest']='boot-before.json'
        with self.assertRaises(Fault): flow.guided_review(self.run,self.state,put(self.run,'review07.json',report))
        d['cold_boot']={'default_oc_observed':True, 'active_efi_evidence':'evidence/fixture.txt',
            **{os:{'usb_removed':True,'success':True,'evidence':'evidence/fixture.txt'} for os in ('macos','windows')}}
        put(self.run,'boot-after.json',d); report['boot_manifest']='boot-after.json'
        flow.guided_review(self.run,self.state,put(self.run,'review07-final.json',report))
        self.assertEqual(self.state['phase'],'08-delivery')

    def test_old_boot_phase_rewinds_for_audit_without_mutating_previous_state(self):
        profile=flow.read_json(flow.UPGRADE_PATH)['from']['0.2.9']
        self.state.update(version='0.2.9',sources=copy.deepcopy(profile['sources']),phase='07-boot')
        flow.save(self.run,self.state,'synthetic-old-phase')
        flow.upgrade(self.run,self.state)
        self.assertEqual(self.state['phase'],'06-devices')
        backup=flow.read_json(self.run/self.state['upgrades'][-1]['backup']['path'])
        self.assertEqual(backup['phase'],'07-boot')
        self.assertEqual(backup['sources'],profile['sources'])


if __name__ == '__main__': unittest.main()
