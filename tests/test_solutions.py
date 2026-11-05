import copy
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'macos-remote-install/scripts'
sys.path.insert(0, str(SCRIPTS))
import solutions
import workflow as flow
from ssh_transport import Fault


class SolutionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.run = Path(tmp.name) / 'run'
        self.state = flow.initialize(self.run)
        self.state.update(phase='06-devices', step='guided-contract')
        flow.save(self.run, self.state, 'synthetic-test')
        self.target = '10EC:8127'
        self.hw = self.write('inventory/device.txt', 'synthetic pci enumeration')
        self.ev = self.write('evidence/source.txt', 'synthetic upstream matching table')
        self.plan = solutions.lookup('ethernet', self.target)['template']
        self.plan.update(environment='synthetic x86_64 build', hardware_evidence=self.hw)
        self.plan['candidates'][0].update(status='excluded', fit='no matching baseline in fixture', evidence=self.hw)
        self.plan['candidates'][1].update(status='usable', revision='commit-fixture', fit='matched architecture and board', evidence=self.ev)
        self.path = self.write('evidence/route.json', self.plan)

    def write(self, name, data):
        file = self.run / name
        file.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            file.write_bytes(data)
        else:
            file.write_text(data if isinstance(data, str) else json.dumps(data), encoding='utf-8')
        return name

    def test_hardware_routing_returns_project_and_usable_template(self):
        self.assertIn('stefb69', self.plan['candidates'][1]['source'])
        self.assertIn('RapidEFI', solutions.lookup('efi','fixture')['cards'][0]['source'])
        self.assertIn('WhateverGreen', solutions.lookup('gpu','1002:fixture')['cards'][0]['source'])
        self.assertIn('USBToolBox', solutions.lookup('usb','fixture')['cards'][0]['source'])
        self.assertEqual(solutions.assess(self.run,self.path)['kind'], 'project')

    def test_unreviewed_baseline_blocks_project_and_matched_baseline_wins(self):
        row = self.plan['candidates'][0]
        row.update(status='unchecked')
        self.write(self.path,self.plan)
        with self.assertRaises(Fault): solutions.assess(self.run,self.path)
        row.update(status='usable',revision='same-machine-snapshot')
        self.write(self.path,self.plan)
        self.assertEqual(solutions.assess(self.run,self.path)['kind'],'baseline')

    def test_efi_template_requires_both_generators_be_considered(self):
        p=solutions.lookup('efi','board')['template']
        p.update(environment='target build',hardware_evidence=self.hw)
        for c in p['candidates']:
            c.update(status='excluded',fit='examined fixture; cannot use this source',evidence=self.ev)
        p['candidates'].append({'kind':'recipe','source':'https://example.org/documentation',
                                'revision':'pinned-doc-sha','fit':'matching official recipe',
                                'evidence':self.ev,'status':'usable','base_config':'staging/original.plist'})
        missing=copy.deepcopy(p); missing['candidates'].pop(2)
        self.write(self.path,missing)
        with self.assertRaises(Fault): solutions.assess(self.run,self.path,topic='efi')
        self.write(self.path,p)
        self.assertEqual(solutions.assess(self.run,self.path,topic='efi')['kind'],'recipe')
        with self.assertRaises(Fault): solutions.assess(self.run,self.path,require_efi=True)
        self.write('staging/original.plist',b'an upstream URL is not a generated file')
        with self.assertRaises(Fault): solutions.assess(self.run,self.path,require_efi=True)
        self.write('staging/original.plist',plistlib.dumps({'ACPI':{},'Kernel':{},'UEFI':{}}))
        self.assertTrue(solutions.assess(self.run,self.path,require_efi=True)['proofs'])

    def test_unpinned_or_missing_or_outside_evidence_cannot_register(self):
        for change in ({'evidence':'../unrelated'},{'revision':'latest'},{'fit':''},{'source':'file:///tmp/example'}):
            p=copy.deepcopy(self.plan); p['candidates'][1].update(change)
            self.write(self.path,p)
            with self.subTest(change=change), self.assertRaises(Fault):
                flow.select_source(self.run,self.state,self.run/self.path)
            self.assertNotIn('source_decisions',self.state)

    def test_real_cli_registers_then_renders_stage_three(self):
        self.state.update(phase='03-media')
        flow.save(self.run,self.state,'switch-to-media')
        p=copy.deepcopy(self.plan);p['topic']='efi'
        p['candidates'][1].update(source=solutions.CARDS['efi'][0]['source'],base_config='staging/original/EFI/OC/config.plist')
        self.write(self.path,p)
        command=[sys.executable,'-B',str(SCRIPTS/'workflow.py'),'--run',str(self.run),'--json']
        def cli(*args):
            r=subprocess.run(command+list(args),capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            return json.loads(r.stdout)
        # Keep child stdout portable for Windows.
        import os
        from unittest.mock import patch
        with patch.dict(os.environ,{'PYTHONIOENCODING':'utf-8'}):
            self.assertEqual(cli('status')['next_action'],'choose-efi')
            selected = cli('choose-efi','--choice','a')
            self.assertEqual(selected['next_action'],'lookup-then-select-source')
            saved=cli('select-source','--file',str(self.run/self.path))
            self.assertEqual(saved['selected_source']['kind'],'project')
            self.assertEqual(cli('status')['next_action'],'guided-contract')

    def test_fresh_media_requires_explicit_choice_before_registering_source(self):
        self.state.update(phase='03-media')
        with self.assertRaises(Fault) as error:
            flow.select_source(self.run,self.state,self.run/self.path)
        self.assertEqual(error.exception.code,'EFI_ROUTE_REQUIRED')
        output=flow.render_result(self.state)
        self.assertEqual([o['value'] for o in output['options']],['a','b','c'])
        self.assertIn('推荐',output['options'][0]['label'])

    def test_manual_and_similar_choices_use_the_selected_evidence(self):
        p=solutions.lookup('efi','board')['template']
        p.update(environment='target build',hardware_evidence=self.hw)
        for source,route in [('https://github.com/example/board-efi','b'),('https://github.com/acidanthera/OpenCorePkg/blob/v-fixture/Docs/Sample.plist','c')]:
            with self.subTest(route=route):
                plan=copy.deepcopy(p)
                plan['candidates'].append({'kind':'recipe','source':source,'revision':'commit-fixture',
                    'fit':'explicit user route and matching hardware','evidence':self.ev,'status':'usable',
                    'base_config':'staging/original.plist'})
                self.write(self.path,plan)
                chosen=solutions.assess(self.run,self.path,topic='efi',efi_route=route)
                self.assertEqual(chosen['source'],source)
                with self.assertRaises(Fault):
                    solutions.assess(self.run,self.path,topic='efi',efi_route='a')

    def test_efi_choice_is_persistent_and_its_evidence_cannot_change(self):
        self.state.update(phase='03-media')
        flow.choose_efi(self.run,self.state,'a')
        self.assertEqual(flow.efi_choice(self.run,flow.load(self.run)),'a')
        revision=self.state['revision']
        flow.choose_efi(self.run,self.state,'a')
        self.assertEqual(self.state['revision'],revision)
        self.write(self.state['efi_choice']['proof']['path'],{'choice':'b'})
        with self.assertRaises(Fault) as error:
            flow.select_source(self.run,self.state,self.run/self.path)
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')

    def test_existing_registered_media_source_resumes_without_a_new_choice(self):
        self.state.update(phase='03-media',source_decisions={'03-media':{'old-plan.json':{'topic':'efi'}}})
        self.assertEqual(flow.render_result(self.state)['next_action'],'guided-contract')
        self.assertNotIn('options',flow.render_result(self.state))

    def test_user_route_change_archives_prior_choice_and_keeps_retry_budget(self):
        self.state.update(phase='03-media')
        flow.choose_efi(self.run,self.state,'a')
        plan=copy.deepcopy(self.plan)
        plan['topic']='efi'
        plan['candidates'][1].update(source=solutions.CARDS['efi'][0]['source'],base_config='staging/original.plist')
        self.write(self.path,plan)
        selected=flow.select_source(self.run,self.state,self.run/self.path)
        self.state['source_trials']={selected['trial_key']:2}
        flow.choose_efi(self.run,self.state,'b')
        self.assertEqual(flow.render_result(self.state)['next_action'],'lookup-then-select-source')
        self.assertEqual(self.state['source_trials'][selected['trial_key']],2)
        saved=self.state['superseded_efi_sources'][-1]
        flow.verify_evidence(self.run,saved)
        self.assertIn(self.path,flow.read_json(self.run/saved['path']))
        with self.assertRaises(Fault):
            flow.select_source(self.run,self.state,self.run/self.path)

    def test_third_same_source_attempt_rejected_even_if_file_and_wording_change(self):
        flow.select_source(self.run,self.state,self.run/self.path)
        issue=self.write('evidence/issue.json',{'code':'NO_INTERFACE','evidence':[self.hw]})
        plan={'target':self.target,'hypothesis':'source mismatch','proposed_change':'trial on copy',
              'expected_result':'interface ready','rollback':'restore baseline','evidence':[self.ev],'source_plan':self.path}
        for n in range(2):
            flow.problem(self.run,self.state,self.run/issue)
            flow.diagnosis(self.run,self.state,self.run/self.write(f'p{n}.json',plan))
            result={'outcome':'rolled-back','evidence':[self.write(f'observation{n}.txt',f'run {n} unchanged')]}
            flow.repair_result(self.run,self.state,self.run/self.write(f'r{n}.json',result))
        flow.problem(self.run,self.state,self.run/issue)
        plan['proposed_change']='renamed guess'
        with self.assertRaises(Fault) as err: flow.diagnosis(self.run,self.state,self.run/self.write('p3.json',plan))
        self.assertEqual(err.exception.code,'SOLUTION_RETRY_LIMIT')
        handoff=err.exception.details['handoff']
        self.assertEqual(handoff['target'],self.target)
        self.assertEqual([x['outcome'] for x in handoff['recent_attempts']],['rolled-back','rolled-back'])
        for item in handoff['recent_attempts']:
            flow.verify_evidence(self.run,item['result'])
            flow.verify_evidence(self.run,item['plan'])
        duplicate=self.write('different-plan-name.json',self.plan)
        with self.assertRaises(Fault): flow.select_source(self.run,self.state,self.run/duplicate)
        self.plan['hardware_evidence']=self.write('inventory/new-hardware.txt','new synthetic boot trace with actual different observations')
        new=self.write('new-facts.json',self.plan)
        flow.select_source(self.run,self.state,self.run/new)
        plan['source_plan']=new
        flow.diagnosis(self.run,self.state,self.run/self.write('reassessed.json',plan))
        self.assertEqual(self.state['step'],'repair')

    def test_missing_registration_or_changed_original_evidence_blocks_device_review(self):
        checks={k:{'result':'pass','basis':'tool','evidence':[self.ev]} for k in flow.PHASES['06-devices']['verification']}
        report={'phase':'06-devices','checks':checks,'source_plans':[self.path]}
        p=self.run/self.write('review.json',report)
        with self.assertRaises(Fault): flow.guided_review(self.run,self.state,p)
        flow.select_source(self.run,self.state,self.run/self.path)
        self.write(self.ev,'changed after selection')
        with self.assertRaises(Fault) as err: flow.guided_review(self.run,self.state,p)
        self.assertEqual(err.exception.code,'EVIDENCE_CHANGED')

    def test_unmodified_hardware_review_can_advance_with_explicit_reason(self):
        checks={k:{'result':'pass','basis':'human','evidence':[self.ev]} for k in flow.PHASES['06-devices']['verification']}
        report={'phase':'06-devices','checks':checks,'source_plans':[]}
        with self.assertRaises(Fault): flow.guided_review(self.run,self.state,self.run/self.write('review.json',report))
        report['no_driver_changes']='All required devices used the installed drivers; functional tests recorded'
        flow.guided_review(self.run,self.state,self.run/self.write('review.json',report))
        self.assertEqual(self.state['phase'],'07-boot')
