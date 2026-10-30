import copy,json,plistlib,struct,sys,tempfile,unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'macos-remote-install/scripts'))
import workflow as flow
from acpi_guard import check_acpi_evidence
from agentkit import sha
from ssh_transport import Fault

MACHINE={'host':'EXAMPLE-PC','user':'example-pc\\tester','uuid':'12345678-1234-1234-1234-123456789abc'}

def synthetic_table(signature):
    data=bytearray(struct.pack('<4sIBB6s8sI4sI',signature,37,2,0,b'TEST  ',b'SYNTHETC',1,b'TEST',1)+b'\xa3')
    data[9]=(-sum(data))%256
    return bytes(data)


class ACPIGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.run=Path(self.tmp.name)/'case';self.state=flow.initialize(self.run)
        self.state.update(phase='03-media',step='guided-contract',machine_a=copy.deepcopy(MACHINE))
        self.raw=self.put('inventory/acpi/DSDT.aml',synthetic_table(b'DSDT'))
        self.patch=self.put('staging/EFI/OC/ACPI/Test.aml',synthetic_table(b'SSDT'))
        self.config=self.put('staging/EFI/OC/config.plist',plistlib.dumps({'ACPI':{'Add':[{'Enabled':True,'Path':'Test.aml'}]},'Misc':{'Debug':{'Target':67,'AppleDebug':True}}}))
        self.capture=self.put('evidence/capture.txt',b'Synthetic Windows capture fixture; not real hardware')
        self.assessment=self.put('evidence/assessment.txt',b'Synthetic namespace and firmware review')
        self.manifest={'schema':'acpi-evidence-v1','machine_uuid':MACHINE['uuid'],'method':'windows-python',
                       'tables':[self.ref(self.raw)],'config':self.ref(self.config),'capture_log':self.ref(self.capture),
                       'assessment':self.ref(self.assessment),'patches':[dict(self.ref(self.patch),based_on=[self.rel(self.raw)],reason='Synthetic fixture') ]}

    def put(self,name,data):
        path=self.run/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path
    def rel(self,path): return path.relative_to(self.run).as_posix()
    def ref(self,path): return {'path':self.rel(path),'sha256':sha(path)['sha256']}
    def write_manifest(self):
        path=self.put('inventory/acpi/collection.json',json.dumps(self.manifest).encode());return self.rel(path)
    def review(self,include_acpi=True):
        checks={key:{'result':'pass','basis':'tool','evidence':[self.rel(self.capture)]} for key in flow.PHASES['03-media']['verification']}
        if include_acpi: checks['acpi_tables']['manifest']=self.write_manifest()
        return self.put('review.json',json.dumps({'phase':'03-media','checks':checks}).encode())

    def test_real_table_bytes_and_matching_efi_can_advance(self):
        flow.guided_review(self.run,self.state,self.review())
        self.assertEqual(self.state['phase'],'04-install')
        paths=[p['path'] for p in self.state['verification_proofs']]
        self.assertIn(self.rel(self.raw),paths);self.assertIn(self.rel(self.patch),paths)

    def test_written_pass_without_tables_cannot_advance(self):
        with self.assertRaises(Fault): flow.guided_review(self.run,self.state,self.review(False))
        self.assertEqual(self.state['phase'],'03-media')

    def test_bad_bytes_rejected_even_if_hash_matches(self):
        for data in (b'',b'ACPI dump succeeded',b'X'*200,synthetic_table(b'SSDT'),synthetic_table(b'DSDT')+b'x'):
            with self.subTest(data=data[:10]):
                self.raw.write_bytes(data);self.manifest['tables']=[self.ref(self.raw)]
                with self.assertRaises(Fault): check_acpi_evidence(self.run,MACHINE,self.write_manifest())

    def test_corrupt_checksum_is_rejected(self):
        data=bytearray(synthetic_table(b'DSDT'));data[-1]^=1
        self.raw.write_bytes(data);self.manifest['tables']=[self.ref(self.raw)]
        with self.assertRaises(Fault): check_acpi_evidence(self.run,MACHINE,self.write_manifest())

    def test_different_target_identity_is_rejected(self):
        self.manifest['machine_uuid']='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        with self.assertRaises(Fault): check_acpi_evidence(self.run,MACHINE,self.write_manifest())

    def test_missing_enabled_patch_or_source_basis_is_rejected(self):
        original=copy.deepcopy(self.manifest)
        for changes in ({'patches':[]},{'patches':[dict(original['patches'][0],based_on=['other.aml'])]}):
            self.manifest=original|changes
            with self.assertRaises(Fault): check_acpi_evidence(self.run,MACHINE,self.write_manifest())

    def test_changed_config_requires_new_assessment(self):
        self.config.write_bytes(plistlib.dumps({'ACPI':{'Add':[]}}))
        with self.assertRaises(Fault): check_acpi_evidence(self.run,MACHINE,self.write_manifest())

    def test_no_custom_add_is_allowed_only_with_explanation(self):
        self.config.write_bytes(plistlib.dumps({'ACPI':{'Add':[]},'Misc':{'Debug':{'Target':67,'AppleDebug':True}}}))
        self.manifest.update(config=self.ref(self.config),patches=[])
        for reason in (None,False,[],{},123,'  '):
            self.manifest['no_add_reason']=reason
            with self.assertRaises(Fault): check_acpi_evidence(self.run,MACHINE,self.write_manifest())
        self.manifest['no_add_reason']='Synthetic reviewed no-patch case'
        self.assertTrue(check_acpi_evidence(self.run,MACHINE,self.write_manifest()))

    def test_malformed_plist_returns_standard_acpi_error(self):
        self.config.write_bytes(b'<?xml version="1.0"?><plist><dict><key>ACPI</key>')
        self.manifest['config']=self.ref(self.config)
        with self.assertRaises(Fault) as caught:
            check_acpi_evidence(self.run,MACHINE,self.write_manifest())
        self.assertEqual(caught.exception.code,'ACPI_EVIDENCE_INVALID')

    def test_screen_only_logging_cannot_pass_first_boot_gate(self):
        config=plistlib.loads(self.config.read_bytes())
        for target,apple_debug in ((3,True),(64,True),(67,False),(True,True)):
            config['Misc']['Debug'].update(Target=target,AppleDebug=apple_debug)
            self.config.write_bytes(plistlib.dumps(config));self.manifest['config']=self.ref(self.config)
            with self.assertRaises(Fault) as caught:
                flow.guided_review(self.run,self.state,self.review())
            self.assertEqual(caught.exception.code,'EFI_DIAGNOSTICS_INVALID')
            self.assertEqual(self.state['phase'],'03-media')
            result=flow.render_result(self.state,{'code':'EFI_DIAGNOSTICS_INVALID'})
            self.assertEqual(result['next_action'],'correct-efi-then-review')

    def test_sysreport_route_needs_choice_evidence(self):
        self.manifest['method']='opencore-sysreport'
        with self.assertRaises(Fault): check_acpi_evidence(self.run,MACHINE,self.write_manifest())
        choice=self.put('evidence/user-choice.txt',b'Synthetic user selects SysReport')
        self.manifest['user_choice']=self.ref(choice)
        self.assertTrue(check_acpi_evidence(self.run,MACHINE,self.write_manifest()))

    def test_later_evidence_tampering_invalidates_completed_stage(self):
        flow.guided_review(self.run,self.state,self.review())
        self.raw.write_bytes(b'changed')
        with self.assertRaises(Fault): flow.load(self.run)

    def seed_legacy(self,phase):
        reviews=[]
        for prior in ('01-hardware','02-storage')+ (('03-media',) if phase=='04-install' else ()):
            proof=flow.evidence(self.run,'legacy-review',{'phase':prior,'synthetic':True})
            reviews.append({'phase':prior,'meaning':'agent-and-human-reviewed; not automatically verified','limited':False,'report':proof,'proofs':[]})
        profile=flow.read_json(flow.UPGRADE_PATH)['from']['0.2.2']
        self.state.update(version='0.2.2',sources=profile['sources'],phase=phase,guided_reviews=reviews,
                          verification_proofs=[r['report'] for r in reviews])
        flow.save(self.run,self.state,'synthetic-legacy-state')

    def test_upgrade_at_03_keeps_completed_storage_reviews(self):
        self.seed_legacy('03-media');before=copy.deepcopy(self.state['guided_reviews'])
        flow.upgrade(self.run,self.state)
        current=flow.load(self.run)
        self.assertEqual(current['phase'],'03-media');self.assertEqual(current['guided_reviews'],before)
        self.assertEqual(current['machine_a'],MACHINE)

    def test_upgrade_at_04_returns_to_media_without_erasing_history(self):
        self.seed_legacy('04-install');flow.upgrade(self.run,self.state)
        current=flow.load(self.run)
        self.assertEqual(current['phase'],'03-media')
        self.assertEqual([r['phase'] for r in current['guided_reviews']],['01-hardware','02-storage'])
        self.assertEqual(current['superseded_guided_reviews'][0]['phase'],'03-media')
        with self.assertRaises(Fault): flow.guided_review(self.run,current,self.review(False))

    def test_upgrade_does_not_silently_rewind_later_install_stages(self):
        self.seed_legacy('04-install');self.state['phase']='05-macos-remote'
        with self.assertRaises(Fault): flow.upgrade(self.run,self.state)


if __name__=='__main__': unittest.main()
