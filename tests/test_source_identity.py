import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'macos-remote-install/scripts'))
import workflow as flow
from ssh_transport import Fault


class SourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.run=self.root/'run';self.state=flow.initialize(self.run)

    def test_text_source_line_endings_share_identity(self):
        path=self.root/'source.py';path.write_bytes(b'one\ntwo\n')
        expected=flow.source_sha(path)
        for data in (b'one\r\ntwo\r\n',b'one\r\ntwo\n'):
            path.write_bytes(data);self.assertEqual(flow.source_sha(path),expected)

    def test_content_bom_whitespace_and_lone_cr_are_not_ignored(self):
        path=self.root/'source.py';path.write_bytes(b'one\ntwo\n');expected=flow.source_sha(path)
        for data in (b'one \ntwo\n',b'\xef\xbb\xbfone\ntwo\n',b'one\rtwo\n',b'one\nthree\n'):
            path.write_bytes(data);self.assertNotEqual(flow.source_sha(path),expected)

    def test_switch_checkout_line_endings_allows_resume_but_edit_does_not(self):
        paths={name:flow.ROOT/name for name in flow.TRACKED}|{'workflow.json':flow.CONTRACT_PATH,'upgrades.json':flow.UPGRADE_PATH}
        scripts=self.root/'checkout/scripts';scripts.mkdir(parents=True)
        for name,original in paths.items():
            target=scripts/name if name in flow.TRACKED else scripts.parent/name
            target.write_bytes(original.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
        with patch.object(flow,'ROOT',scripts),patch.object(flow,'CONTRACT_PATH',scripts.parent/'workflow.json'),patch.object(flow,'UPGRADE_PATH',scripts.parent/'upgrades.json'):
            self.assertEqual(flow.load(self.run)['sources'],self.state['sources'])
            with (scripts/'workflow.py').open('ab') as f:f.write(b'# local modification\r\n')
            with self.assertRaises(Fault) as caught:flow.load(self.run)
            self.assertEqual(caught.exception.code,'SOURCE_CHANGED')

    def test_old_crlf_task_upgrades_without_editing_recorded_hashes(self):
        profiles=flow.read_json(flow.UPGRADE_PATH)['from']
        for version in ('0.2.0','0.2.1','0.2.2','0.2.3'):
            with self.subTest(version=version):
                run=self.root/version;state=flow.initialize(run)
                profile=profiles[version];sources=copy.deepcopy(profile['sources'])
                for name,variants in profile['source_variants'].items():sources[name]=variants[-1]
                state.update(version=version,sources=sources,phase='03-media',step='guided-contract')
                flow.save(run,state,'legacy-crlf-fixture');old=copy.deepcopy(state)
                flow.upgrade(run,state);current=flow.load(run)
                original=flow.read_json(run/current['upgrades'][-1]['backup']['path'])
                self.assertEqual(original['sources'],old['sources'])
                self.assertEqual(current['source_hash_mode'],'utf8-lf-v1')
                self.assertEqual(current['phase'],'03-media')

    def test_unknown_single_source_hash_is_rejected_without_state_mutation(self):
        profile=flow.read_json(flow.UPGRADE_PATH)['from']['0.2.2']
        self.state.update(version='0.2.2',sources=copy.deepcopy(profile['sources']))
        self.state['sources']['agentkit.py']='0'*64;before=copy.deepcopy(self.state)
        with self.assertRaises(Fault):flow.upgrade(self.run,self.state)
        self.assertEqual(self.state,before)

    def test_evidence_hashes_remain_byte_exact(self):
        proof=flow.evidence(self.run,'data',{'text':'example'})
        path=self.run/proof['path'];path.write_bytes(path.read_bytes().replace(b'\n',b'\r\n'))
        with self.assertRaises(Fault) as caught:flow.verify_evidence(self.run,proof)
        self.assertEqual(caught.exception.code,'EVIDENCE_CHANGED')

    def test_023_completed_media_is_not_rewound_by_hash_only_upgrade(self):
        profile=flow.read_json(flow.UPGRADE_PATH)['from']['0.2.3']
        self.state.update(version='0.2.3',sources=copy.deepcopy(profile['sources']),phase='04-install',step='guided-contract')
        flow.upgrade(self.run,self.state)
        self.assertEqual(flow.load(self.run)['phase'],'04-install')


if __name__=='__main__':unittest.main()
