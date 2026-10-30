import copy
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'macos-remote-install/scripts'
sys.path.insert(0,str(SCRIPTS))
import agentkit
import workflow as flow
import ssh_transport as ssh

try:
    import paramiko
except ImportError:
    paramiko=None


def packet(**changes):
    data={'schema':'ssh-handoff-v1','stage':'00','status':'local-ready','host':'EXAMPLE-PC',
          'user':'example-pc\\testuser','port':22,'ipv4':[{'ip':'198.51.100.20'}],
          'host_keys':[{'algorithm':'ED25519','sha256':'SHA256:'+'A'*43}],
          'checks':{'service':'Running','startup':'Auto'}}
    data.update(changes)
    return 'SSH_HANDOFF_V1 '+json.dumps(data)


IDENTITY={'host':'EXAMPLE-PC','user':'example-pc\\testuser','uuid':'12345678-1234-1234-1234-123456789abc','os':'Windows','admin':True}


def good_result(*args,**kwargs):
    return {'schema':'remote-verification-v1','identity':dict(IDENTITY),'address':'198.51.100.20','port':22,
            'fingerprint':'SHA256:'+'A'*43,'checks':{k:True for k in ('ssh','host_key','identity','admin','sftp')}}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='workflow-test-')
        self.addCleanup(self.temp.cleanup)
        self.run=Path(self.temp.name)/'runs'/'case'
        self.state=flow.initialize(self.run)

    def write(self,name,value):
        path=self.run/name
        path.write_text(value if isinstance(value,str) else json.dumps(value),encoding='utf-8')
        return path

    def import_good(self):
        flow.import_handoff(self.run,self.state,self.write('handoff.txt',packet()))

    def test_init_creates_parent_and_resume_does_not_reset(self):
        first=self.state['run_id']
        self.import_good()
        state=flow.initialize(self.run)
        self.assertEqual(state['run_id'],first)
        self.assertEqual(state['step'],'verify')

    def test_prepare_has_one_ip_change_and_is_not_execution(self):
        flow.prepare(self.run,self.state,['198.51.100.2'])
        output=flow.render_result(self.state)
        code=(self.run/output['script']['path']).read_text(encoding='utf-8-sig')
        self.assertEqual(code,flow.render(flow.SOURCE.read_text(encoding='utf-8-sig'),['198.51.100.2']))
        self.assertEqual(output['next_action'],'import')
        self.assertEqual(output['display'].count('\n'),2)
        self.assertIsNone(self.state['packet'])

    def test_existing_packet_skips_setup_and_requires_actual_connection(self):
        self.import_good()
        self.assertNotIn('prepared',self.state)
        self.assertEqual(self.state['phase'],'00-remote')
        flow.verify(self.run,self.state,verifier=good_result)
        self.assertEqual(self.state['phase'],'01-hardware')
        self.assertEqual(len(self.state['verification_proofs']),2)

    def test_boolean_claim_cannot_replace_missing_connection_checks(self):
        self.import_good()
        flow.verify(self.run,self.state,verifier=lambda *a,**k:{'schema':'remote-verification-v1','checks':{'ssh':True}})
        self.assertEqual(self.state['phase'],'00-remote')
        self.assertEqual(self.state['failure']['code'],'REMOTE_OUTPUT_INVALID')

    def test_generic_checkpoint_cannot_advance_managed_run(self):
        self.write('evidence/fake.json',{})
        with self.assertRaises(ValueError):
            agentkit.checkpoint(self.run,'08-delivery','verified','pretend',['evidence/fake.json'])
        self.assertEqual(flow.load(self.run)['phase'],'00-remote')

    def test_packet_filters_extra_password_field(self):
        secret='SYNTHETIC_DO_NOT_LOG'
        flow.import_handoff(self.run,self.state,self.write('handoff.txt',packet(password=secret)))
        self.assertNotIn(secret,(self.run/'workflow-state.json').read_text(encoding='utf-8'))
        for path in (self.run/'evidence').glob('*.json'):
            self.assertNotIn(secret,path.read_text(encoding='utf-8'))

    def test_failed_setup_is_not_reinstalled_automatically(self):
        text=packet(status='failed',failed_step='生成连接信息',error='private raw error')
        with self.assertRaises(ssh.Fault) as caught:
            flow.import_handoff(self.run,self.state,self.write('failed.txt',text))
        self.assertEqual(caught.exception.code,'FINGERPRINT_READ_FAILED')
        self.assertIsNone(self.state['packet'])

    def test_no_skipping_from_00_using_guided_report(self):
        with self.assertRaises(ssh.Fault):
            flow.guided_review(self.run,self.state,self.write('report.json',{'phase':'08-delivery'}))

    def test_two_failures_need_new_diagnostic_evidence(self):
        self.import_good()
        def fail(*a,**k): raise ssh.Fault('SSH_TIMEOUT')
        flow.verify(self.run,self.state,verifier=fail)
        flow.verify(self.run,self.state,verifier=fail)
        with self.assertRaises(ssh.Fault) as caught:
            flow.verify(self.run,self.state,verifier=fail)
        self.assertEqual(caught.exception.code,'RETRY_LIMIT')
        self.assertEqual(self.state['phase'],'00-remote')

    def test_repair_does_not_mark_success_and_returns_to_original_check(self):
        self.import_good()
        def fail(*a,**k): raise ssh.Fault('SSH_REFUSED')
        flow.verify(self.run,self.state,verifier=fail)
        self.write('evidence/problem.txt','Service stopped, synthetic evidence')
        plan={'hypothesis':'stopped service','target':'A sshd','proposed_change':'start existing service',
              'expected_result':'22 listening','rollback':'restore prior state','evidence':['evidence/problem.txt']}
        flow.diagnosis(self.run,self.state,self.write('plan.json',plan))
        self.assertEqual(flow.render_result(self.state)['next_action'],'repair-result')
        self.write('evidence/repair.txt','Service running, synthetic evidence')
        result={'outcome':'applied','evidence':['evidence/repair.txt']}
        flow.repair_result(self.run,self.state,self.write('repair.json',result))
        self.assertEqual(self.state['phase'],'00-remote')
        self.assertEqual(self.state['step'],'verify')
        flow.verify(self.run,self.state,verifier=good_result)
        self.assertEqual(self.state['phase'],'01-hardware')

    def test_interrupt_requires_resume_not_skipping(self):
        self.import_good()
        self.state['status']='running'
        flow.save(self.run,self.state,'synthetic-interrupt')
        resumed=flow.load(self.run)
        self.assertEqual(flow.render_result(resumed)['next_action'],'resume')
        with self.assertRaises(ssh.Fault):
            flow.verify(self.run,resumed,verifier=good_result)
        flow.resume(self.run,resumed)
        self.assertEqual(resumed['step'],'verify')
        flow.verify(self.run,resumed,verifier=good_result)
        self.assertEqual(resumed['phase'],'01-hardware')

    def test_tampered_evidence_rejects_previous_verified_result(self):
        self.import_good(); flow.verify(self.run,self.state,verifier=good_result)
        proof=self.state['verification_proofs'][-1]
        self.write(proof['path'],{'changed':True})
        with self.assertRaises(ssh.Fault) as caught: flow.load(self.run)
        self.assertEqual(caught.exception.code,'EVIDENCE_CHANGED')

    def test_changed_program_refuses_silent_version_switch(self):
        with patch.object(flow,'source_lock',return_value={'changed':'hash'}):
            with self.assertRaises(ssh.Fault) as caught: flow.load(self.run)
        self.assertEqual(caught.exception.code,'SOURCE_CHANGED')

    def test_recheck_preserves_hardware_identity(self):
        self.import_good(); flow.verify(self.run,self.state,verifier=good_result)
        flow.recheck(self.run,self.state)
        self.assertEqual(self.state['phase'],'00-remote')
        self.assertEqual(self.state['machine_a'],IDENTITY)

    def test_guided_contract_reports_are_distinguished_from_auto_verification(self):
        self.import_good(); flow.verify(self.run,self.state,verifier=good_result)
        self.write('evidence/assessment.txt','Synthetic assessment')
        contract=flow.PHASES['01-hardware']
        report={'phase':'01-hardware','checks':{name:{'result':'pass','basis':'source-review','evidence':['evidence/assessment.txt']} for name in contract['verification']}}
        flow.guided_review(self.run,self.state,self.write('assessment.json',report))
        self.assertEqual(self.state['phase'],'02-storage')
        self.assertIn('not automatically verified',self.state['guided_reviews'][-1]['meaning'])

    def test_storage_identity_cannot_be_accepted_as_limitation(self):
        self.state.update(phase='02-storage',step='guided-contract')
        self.write('evidence/review.txt','Synthetic evidence')
        contract=flow.PHASES['02-storage']
        checks={name:{'result':'pass','basis':'tool','evidence':['evidence/review.txt']} for name in contract['verification']}
        checks['disk_identity'].update(result='accepted-limit',user_acceptance='yes')
        with self.assertRaises(ssh.Fault): flow.guided_review(self.run,self.state,self.write('invalid.json',{'phase':'02-storage','checks':checks}))

    def test_failed_packet_does_not_include_raw_error_in_state(self):
        result=ssh.parse_packet(packet(status='failed',failed_step='生成连接信息',error='secret'))
        self.assertNotIn('secret',json.dumps(result))

    def test_actual_setup_step_names_are_preserved(self):
        for step in ('启动并检查监听','配置防火墙'):
            result=ssh.parse_packet(packet(status='failed',failed_step=step))
            self.assertEqual(result['failed_step'],step)

    def test_local_credential_errors_do_not_consume_remote_attempts(self):
        self.import_good()
        for code in ('CREDENTIAL_REQUIRED','CREDENTIAL_INVALID','DEPENDENCY_MISSING'):
            def fail(*a,**k): raise ssh.Fault(code)
            flow.verify(self.run,self.state,verifier=fail)
            self.assertEqual(self.state['attempt_count'],0)
            flow.resume(self.run,self.state)
        flow.verify(self.run,self.state,verifier=good_result)
        self.assertEqual(self.state['phase'],'01-hardware')

    def test_bad_guided_report_has_repairable_next_action(self):
        self.import_good(); flow.verify(self.run,self.state,verifier=good_result)
        with self.assertRaises(ssh.Fault) as caught:
            flow.guided_review(self.run,self.state,self.write('bad-report.json',{'phase':'01-hardware','checks':{}}))
        flow.record_fault(self.run,self.state,caught.exception)
        self.assertEqual(flow.render_result(self.state)['next_action'],'correct-report-then-review')
        self.write('evidence/good-report.txt','Synthetic assessment')
        checks={name:{'result':'pass','basis':'source-review','evidence':['evidence/good-report.txt']} for name in flow.PHASES['01-hardware']['verification']}
        flow.guided_review(self.run,self.state,self.write('good-report.json',{'phase':'01-hardware','checks':checks}))
        self.assertEqual(self.state['phase'],'02-storage'); self.assertIsNone(self.state['failure'])

    def test_guided_problem_repair_returns_to_same_phase(self):
        self.import_good(); flow.verify(self.run,self.state,verifier=good_result)
        self.write('evidence/error.txt','Synthetic failed collector')
        flow.problem(self.run,self.state,self.write('problem.json',{'code':'COLLECTOR_FAILED','evidence':['evidence/error.txt']}))
        plan={'hypothesis':'encoding mismatch','target':'collector invocation','proposed_change':'correct encoding','expected_result':'parseable output','rollback':'restore invocation','evidence':['evidence/error.txt']}
        flow.diagnosis(self.run,self.state,self.write('plan.json',plan))
        self.write('evidence/fixed.txt','Synthetic corrected invocation, not acceptance')
        flow.repair_result(self.run,self.state,self.write('fixed.json',{'outcome':'applied','evidence':['evidence/fixed.txt']}))
        self.assertEqual(self.state['phase'],'01-hardware'); self.assertEqual(self.state['step'],'guided-contract')
        self.assertFalse(self.state.get('guided_reviews'))

    def test_restart_recovery_keeps_explicit_human_reboot_instruction(self):
        flow.record_fault(self.run,self.state,ssh.Fault('RESTART_REQUIRED'))
        flow.recover(self.run,self.state)
        output=flow.render_result(self.state)
        self.assertEqual(output['next_action'],'import')
        self.assertIn('重启 A',output['display'])
        self.assertEqual(output['display'].count('\n'),2)

    def test_repeated_fixed_recovery_is_bounded(self):
        for _ in range(2):
            flow.record_fault(self.run,self.state,ssh.Fault('SSH_TIMEOUT'))
            flow.recover(self.run,self.state)
        flow.record_fault(self.run,self.state,ssh.Fault('SSH_TIMEOUT'))
        with self.assertRaises(ssh.Fault) as caught: flow.recover(self.run,self.state)
        self.assertEqual(caught.exception.code,'RETRY_LIMIT')

    def test_all_contracts_have_fixed_order_and_explicit_acceptance(self):
        phases=list(flow.PHASES.values())
        self.assertEqual(len(phases),9)
        for i,phase in enumerate(phases):
            for field in ('inputs','preconditions','actions','verification','failure_route','resume'):
                self.assertTrue(phase[field])
            self.assertEqual(phase['next'],phases[i+1]['id'] if i+1<len(phases) else None)

    def test_bundle_password_is_used_without_another_credential_argument(self):
        secret='  SYNTHETIC-"quote"-\\-$(literal)-密码  '
        text=ssh.CREDENTIAL_MARKER+secret+'\n'+packet()
        flow.import_handoff(self.run,self.state,self.write('private-input.txt',text))
        captured=[]
        def verify(*args,**kwargs):
            captured.append(ssh.read_secret(kwargs['credential_file']))
            return good_result()
        flow.verify(self.run,self.state,verifier=verify)
        self.assertEqual(captured,[secret])
        for path in [self.run/'workflow-state.json',self.run/'state.json',self.run/'workflow-events.jsonl',*(self.run/'evidence').glob('*.json')]:
            self.assertNotIn('SYNTHETIC-',path.read_text(encoding='utf-8'))

    def test_bundle_file_path_with_spaces_needs_no_json_escaping(self):
        password_file=self.write('账号 信息.txt','用户名：admin\n密码：SYNTHETIC-FILE-PASSWORD\n')
        text=ssh.CREDENTIAL_MARKER+'"'+str(password_file)+'"\n'+packet()
        flow.import_handoff(self.run,self.state,self.write('input.txt',text))
        self.assertEqual(ssh.read_secret(self.run/'private/a-login-password'),'SYNTHETIC-FILE-PASSWORD')

    def test_placeholder_does_not_become_password_or_erase_existing_credential(self):
        flow.import_handoff(self.run,self.state,self.write('initial.txt',ssh.CREDENTIAL_MARKER+'SYNTHETIC-EXISTING\n'+packet()))
        for marker in (ssh.CREDENTIAL_PLACEHOLDER,'已提供'):
            flow.import_handoff(self.run,self.state,self.write('later.txt',ssh.CREDENTIAL_MARKER+marker+'\n'+packet()))
            self.assertEqual(ssh.read_secret(self.run/'private/a-login-password'),'SYNTHETIC-EXISTING')

    def test_unfilled_placeholder_with_no_saved_password_is_not_authenticated(self):
        flow.import_handoff(self.run,self.state,self.write('placeholder.txt',ssh.CREDENTIAL_MARKER+ssh.CREDENTIAL_PLACEHOLDER+'\n'+packet()))
        self.assertFalse((self.run/'private/a-login-password').exists())

    def test_missing_credential_file_preserves_connection_information(self):
        text=ssh.CREDENTIAL_MARKER+str(self.run/'missing.txt')+'\n'+packet()
        with self.assertRaises(ssh.Fault) as caught: flow.import_handoff(self.run,self.state,self.write('input.txt',text))
        self.assertEqual(caught.exception.code,'CREDENTIAL_INVALID')
        self.assertEqual(self.state['step'],'verify')
        self.assertEqual(self.state['packet']['host'],'EXAMPLE-PC')

    def test_known_020_upgrade_preserves_task_and_saves_backup(self):
        self.import_good()
        old=flow.read_json(flow.UPGRADE_PATH)['from']['0.2.0']
        self.state.update(version='0.2.0',sources=old['sources'])
        original_id=self.state['run_id']
        flow.save(self.run,self.state,'synthetic-old-task')
        with self.assertRaises(ssh.Fault): flow.load(self.run)
        loaded=flow.load(self.run,check_sources=False)
        flow.upgrade(self.run,loaded)
        current=flow.load(self.run)
        self.assertEqual(current['run_id'],original_id)
        self.assertEqual(current['version'],'0.2.3')
        self.assertEqual(current['step'],'verify')
        flow.verify_evidence(self.run,current['upgrades'][0]['backup'])

    def test_upgrade_rejects_unknown_source_and_running_operation(self):
        profile=flow.read_json(flow.UPGRADE_PATH)['from']['0.2.0']
        self.state.update(version='0.2.0',sources=profile['sources'],status='running')
        with self.assertRaises(ssh.Fault): flow.upgrade(self.run,self.state)
        self.state.update(status='planned',sources={'unknown':'hash'})
        with self.assertRaises(ssh.Fault): flow.upgrade(self.run,self.state)

    def test_021_upgrade_preserves_failed_connection_and_attempt_count(self):
        self.import_good()
        profile=flow.read_json(flow.UPGRADE_PATH)['from']['0.2.1']
        self.state.update(version='0.2.1',sources=profile['sources'],status='failed',attempt_count=1,
                          failure={'code':'SSH_TIMEOUT','details':{},'resume':'verify'})
        flow.save(self.run,self.state,'synthetic-021-failure')
        loaded=flow.load(self.run,check_sources=False)
        flow.upgrade(self.run,loaded)
        current=flow.load(self.run)
        self.assertEqual(current['upgrades'][-1]['from'],'0.2.1')
        self.assertEqual(current['upgrades'][-1]['to'],'0.2.3')
        self.assertEqual(current['attempt_count'],1)
        self.assertEqual(current['packet'],self.state['packet'])
        self.assertEqual(current['step'],'verify')


class IdentityTests(unittest.TestCase):
    def probe(self,**changes):
        value=IDENTITY|{'schema':'windows-ssh-probe-v1','temp':'C:\\Temp'}|changes
        return 'WINDOWS_SSH_PROBE_V1 '+json.dumps(value)

    def test_nonadmin_cannot_pass(self):
        with self.assertRaises(ssh.Fault) as caught:
            ssh.validate_identity(self.probe(admin=False),IDENTITY)
        self.assertEqual(caught.exception.code,'ADMIN_REQUIRED')

    def test_wrong_machine_uuid_is_rejected_after_reconnect(self):
        with self.assertRaises(ssh.Fault) as caught:
            ssh.validate_identity(self.probe(uuid='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'),IDENTITY,IDENTITY)
        self.assertEqual(caught.exception.code,'IDENTITY_MISMATCH')

    def test_invalid_remote_temp_path_is_rejected(self):
        for temp in ('../data','C:\\Temp\\..\\Windows','\\\\server\\share'):
            with self.subTest(temp=temp),self.assertRaises(ssh.Fault): ssh.validate_identity(self.probe(temp=temp),IDENTITY)

    def test_invalid_packet_and_duplicate_packets_are_rejected(self):
        for text in (packet()+'\n'+packet(),packet(port='22'),packet(ipv4=[{'ip':'127.0.0.1'}]),packet(host_keys=[{'sha256':'SHA256:bad'}])):
            with self.subTest(text=text),self.assertRaises(ssh.Fault): ssh.parse_packet(text)

    def test_explicit_password_prefix_preserves_password_that_looks_like_path(self):
        self.assertEqual(ssh.credential_from_bundle('A_LOGIN_CREDENTIAL: 密码=C:\\literal'),'C:\\literal')

    def test_multiple_password_fields_are_not_guessed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'account.txt'
            path.write_text('用户名：x\n密码：one\npassword: two',encoding='utf-8')
            with self.assertRaises(ssh.Fault): ssh.read_secret(path)


if paramiko:
    class MemoryHandle(paramiko.SFTPHandle):
        def __init__(self,store,path):
            super().__init__(); self.store=store; self.path=path
        def read(self,offset,length): return self.store[self.path][offset:offset+length]
        def write(self,offset,data):
            old=self.store[self.path]
            self.store[self.path]=old[:offset]+data+old[offset+len(data):]
            return paramiko.SFTP_OK

    class MemorySFTP(paramiko.SFTPServerInterface):
        def __init__(self,server,*args,**kwargs):
            super().__init__(server,*args,**kwargs); self.store=server.fixture.files
        def open(self,path,flags,attr):
            if flags & os.O_CREAT:
                if path in self.store and flags & os.O_EXCL: return paramiko.SFTP_FAILURE
                self.store[path]=b''
            if path not in self.store: return paramiko.SFTP_NO_SUCH_FILE
            return MemoryHandle(self.store,path)
        def remove(self,path):
            del self.store[path]; return paramiko.SFTP_OK

    class Server(paramiko.ServerInterface):
        def __init__(self,fixture): self.fixture=fixture
        def check_auth_password(self,username,password):
            self.fixture.auth_attempts+=1
            return paramiko.AUTH_SUCCESSFUL if username==IDENTITY['user'] and password=='synthetic-password' else paramiko.AUTH_FAILED
        def get_allowed_auths(self,username): return 'password'
        def check_channel_request(self,kind,chanid): return paramiko.OPEN_SUCCEEDED if kind=='session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
        def check_channel_exec_request(self,channel,command):
            self.fixture.commands.append(command.decode())
            if command.decode()!=ssh.probe_command(): return False
            def respond():
                time.sleep(0.02)
                result=IDENTITY|{'schema':'windows-ssh-probe-v1','temp':'C:\\Temp','admin':self.fixture.admin}
                channel.sendall(('WINDOWS_SSH_PROBE_V1 '+json.dumps(result)+'\n').encode())
                channel.send_exit_status(0); channel.shutdown_write()
            threading.Thread(target=respond,daemon=True).start()
            return True

    class FixtureServer:
        def __init__(self,admin=True):
            self.key=paramiko.RSAKey.generate(2048)
            self.listener=socket.socket()
            self.listener.bind(('127.0.0.1',0)); self.listener.listen(1); self.listener.settimeout(5)
            self.port=self.listener.getsockname()[1]
            self.auth_attempts=0; self.commands=[]; self.files={}; self.admin=admin
            self.stop=threading.Event(); self.transport=None
            self.thread=threading.Thread(target=self.serve,daemon=True); self.thread.start()
        def serve(self):
            try:
                connection,_=self.listener.accept()
                self.transport=paramiko.Transport(connection)
                self.transport.add_server_key(self.key)
                self.transport.set_subsystem_handler('sftp',paramiko.SFTPServer,MemorySFTP)
                self.transport.start_server(server=Server(self))
                self.stop.wait(15)
            except (OSError,EOFError,paramiko.SSHException): pass
        def close(self):
            self.stop.set(); self.listener.close()
            if self.transport: self.transport.close()
            self.thread.join(2)
        def connection_packet(self):
            # Loopback is used only by this isolated test; real imported packets reject it.
            data=ssh.parse_packet(packet())
            data.update(addresses=['127.0.0.1'],port=self.port,fingerprints=[ssh.key_fingerprint(self.key)])
            return data


@unittest.skipUnless(paramiko,'Paramiko required for local SSH integration tests')
class SSHWireTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ssh-wire-')
        self.addCleanup(self.temp.cleanup)
        self.password=Path(self.temp.name)/'credential'
        self.password.write_text('synthetic-password',encoding='utf-8')
    def server(self,**kwargs):
        server=FixtureServer(**kwargs); self.addCleanup(server.close); return server
    def test_real_protocol_pin_auth_command_and_sftp_roundtrip(self):
        server=self.server()
        result=ssh.verify_connection(server.connection_packet(),credential_file=self.password,timeout=3)
        self.assertTrue(all(result['checks'].values()))
        self.assertEqual(result['identity'],IDENTITY)
        self.assertEqual(server.auth_attempts,1)
        self.assertEqual(server.files,{})
        self.assertEqual(server.commands,[ssh.probe_command()])
    def test_wrong_fingerprint_sends_no_password_and_runs_no_commands(self):
        server=self.server(); data=server.connection_packet(); data['fingerprints']=['SHA256:'+'A'*43]
        with self.assertRaises(ssh.Fault) as caught: ssh.verify_connection(data,credential_file=self.password,timeout=3)
        self.assertEqual(caught.exception.code,'HOST_KEY_MISMATCH')
        self.assertEqual(server.auth_attempts,0); self.assertEqual(server.commands,[])
    def test_bad_password_is_not_retried_on_other_addresses(self):
        server=self.server(); data=server.connection_packet(); data['addresses']*=2
        self.password.write_text('wrong-password',encoding='utf-8')
        with self.assertRaises(ssh.Fault) as caught: ssh.verify_connection(data,credential_file=self.password,timeout=3)
        self.assertEqual(caught.exception.code,'AUTH_FAILED')
        self.assertEqual(server.auth_attempts,1)
    def test_nonadmin_never_performs_sftp_write(self):
        server=self.server(admin=False)
        with self.assertRaises(ssh.Fault) as caught: ssh.verify_connection(server.connection_packet(),credential_file=self.password,timeout=3)
        self.assertEqual(caught.exception.code,'ADMIN_REQUIRED'); self.assertEqual(server.files,{})
