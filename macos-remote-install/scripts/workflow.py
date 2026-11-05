"""Deterministic workflow controller. Stage 00 is executable; 01-08 use guided contracts."""
import argparse
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import uuid

from agentkit import confined, init_run, no_link, read_json, sha, utc
from prepare_ssh_handoff import render, SOURCE
from ssh_transport import Fault, parse_packet, verify_connection, credential_from_bundle
from acpi_guard import check_acpi_evidence
from solutions import assess as assess_solution
from postinstall_guard import check_devices, device_queue, check_boot

VERSION = '0.2.10'
ROOT = Path(__file__).resolve().parent
CONTRACT_PATH = ROOT.parent / 'workflow.json'
UPGRADE_PATH = ROOT.parent / 'upgrades.json'
CONTRACT = read_json(CONTRACT_PATH)
PHASES = {p['id']:p for p in CONTRACT['phases']}
TRACKED = ['workflow.py','ssh_transport.py','probe-windows.ps1','enable-windows-ssh.ps1','prepare_ssh_handoff.py','agentkit.py','acpi_guard.py','efi_audit.py','metal_smoke_test.js','solutions.py','postinstall_guard.py','collect-macos.sh']

# code -> summary, diagnostic action, human input, fixed resume action
ERRORS = {
    'DEVICE_AUDIT_REQUIRED': ('还没完成本轮全机检查清单。','我会对照安装前的硬件，补查每件设备和系统功能。','暂时无需操作。','record-devices'),
    'DEVICE_AUDIT_OPEN': ('硬件清单还有待处理或待测项。','我会继续可做的修复，再集中交代仍受限的项目；暂不写入硬盘引导。','需要现场测试或接受限制时，我会一起说明。','record-devices'),
    'BOOT_REGISTRATION_REQUIRED': ('硬盘引导的启动项还没核验完整。','我会核对固件中的硬盘 OpenCore 路径、启动顺序和菜单设置。','先保留 U 盘，等检查完成再拔盘重启。','boot-ready'),
    'EFI_PICKER_INVALID': ('安装 EFI 还在隐藏恢复等辅助条目。','我会在测试副本将 HideAuxiliary 设为 false，重新校验并回读 U 盘。','暂时无需操作。','review'),
    'EFI_ROUTE_REQUIRED': ('备份与安装空间已确认，先选择 EFI 制作方式。','选定后我会按这条路线制作并检查启动文件。','回复 a、b 或 c。','choose-efi'),
    'SOLUTION_REQUIRED': ('还需确认现有方案适合这台电脑。','我会先核对同机成功记录，再比较工具作者提供的方案。','暂时无需操作。','select-source'),
    'SOLUTION_RETRY_LIMIT': ('同一方案在相同条件下已试过两轮。','我会保留可退回的配置，核对新的线索或整理交接，再继续可做的检查。','暂时无需操作。','select-source'),
    'PACKET_INVALID': ('收到的连接结果不完整。','我会用原始结果核对 A。','从 A 的 PowerShell 重新复制完整的 SSH_HANDOFF_V1 那一行到这里。','import'),
    'SETUP_FAILED': ('A 上的远程登录还没配置好。','我会根据出错的位置检查原因。','如果还没发过，请把 A 窗口末尾的结果发来。','prepare'),
    'FINGERPRINT_READ_FAILED': ('还没读到用来辨认 A 的连接指纹。','我会检查读取方式，再给你重试代码。','等代码准备好，再到 A 运行一次。','prepare'),
    'RESTART_REQUIRED': ('Windows 提示安装远程登录功能后需要重启。','我会准备重启后的检查代码。','先保存 A 上打开的文件。','prepare'),
    'DEPENDENCY_MISSING': ('B 上缺一个远程连接工具。','我会在 B 上补齐并重新连接。','暂时无需操作。','verify'),
    'DEPENDENCY_INSTALL_FAILED': ('B 上的远程连接工具没有装好。','我会检查 B 的下载和安装记录。','暂时无需操作。','diagnose'),
    'CREDENTIAL_REQUIRED': ('还缺少 A 的登录方式。','我会用你提供的 Windows 账户登录 A。','提供该账户的登录密码、B 上密码文件的路径，或已有的登录密钥。','verify'),
    'CREDENTIAL_INVALID': ('无法读取给定的登录信息。','我会重新检查文件和内容。','请核对 B 上密码文件的完整路径，或直接提供 A 的账户密码。','verify'),
    'SSH_TIMEOUT': ('B 尝试连接 A，一直没有收到回应。','我会核对地址，并检查远程登录是否被防火墙拦住。','暂时无需操作。如果 A 的安全软件提示拦截 OpenSSH，请允许它在局域网接收连接（TCP 22）。','verify'),
    'SSH_REFUSED': ('A 有回应，但远程登录没有接通。','我会核对 A 的远程登录服务，再准备检查代码。','等代码准备好，再到 A 运行一次。','verify'),
    'SSH_UNREACHABLE': ('B 无法访问 A 提供的网络地址。','我会核对地址，再准备连接检查。','确认两台电脑仍连在同一台路由器上。','verify'),
    'AUTH_FAILED': ('A 没有接受这次账户登录。','我会核对用户名和登录设置，暂停尝试密码。','请核对一次 A 的 Windows 账户密码，PIN 不能代替它。','verify'),
    'HOST_KEY_MISMATCH': ('响应连接的电脑与 A 提供的指纹不一致。','我会先核对电脑身份，再使用登录密码。','等重新检查的代码准备好，在 A 上运行并发回新结果。','import'),
    'IDENTITY_MISMATCH': ('连上的电脑或账户与之前的信息不符。','我会先核对目标，再继续检查。','确认哪台是要装 macOS 的 A，再发来它的连接结果。','import'),
    'IDENTITY_INCOMPLETE': ('尚不能可靠地辨认这台电脑。','我会核对连接记录和硬件标识。','暂时无需操作。','verify'),
    'ADMIN_REQUIRED': ('当前账户远程登录后，缺少管理员权限。','我会核对登录账户和它实际具有的权限。','准备 A 上有管理员权限的 Windows 账户。','verify'),
    'SSH_PROTOCOL_FAILED': ('B 与 A 没能建立远程登录。','我会检查两端的连接工具及服务记录。','暂时无需操作。','verify'),
    'REMOTE_COMMAND_TIMEOUT': ('A 没有及时返回检查结果。','我会检查连接和 A 上的 PowerShell 是否仍有回应。','暂时无需操作。','verify'),
    'REMOTE_PROBE_FAILED': ('已连上 A，但读取系统信息失败。','我会检查 A 的 PowerShell 和系统信息服务。','暂时无需操作。','verify'),
    'REMOTE_OUTPUT_INVALID': ('A 返回的系统信息无法核实。','我会检查读取方式后重试。','暂时无需操作。','verify'),
    'SFTP_FAILED': ('两台电脑之间的文件试传没有通过。','我会检查 A 是否允许传文件和写入临时文件夹。','暂时无需操作。','verify'),
    'SFTP_CLEANUP_FAILED': ('试传文件还没清理完。','我会核对并移除这次检查留下的临时文件。','暂时无需操作。','verify'),
    'RETRY_LIMIT': ('相同条件下的检查已连续失败。','我会根据现有记录查原因，找到新线索再试。','暂时无需操作。','diagnose'),
    'SOURCE_CHANGED': ('当前工具与这次安装开始时使用的版本有差异。','我会核对版本，并保留之前的安装记录。','暂时无需操作。','status'),
    'UPGRADE_UNSUPPORTED': ('这份安装记录暂时无法切换到新版工具。','我会保留旧版本，核对从哪一步可以继续。','暂时无需操作。','status'),
    'RESUME_REQUIRED': ('上一次操作中断了。','我会核对进度，从中断处重新检查。','暂时无需操作。','resume'),
    'STATE_INVALID': ('上一次的进度记录不完整。','我会保留原文件，核对最后完成的步骤。','暂时无需操作。','status'),
    'ACTION_NOT_ALLOWED': ('还没到执行这个动作的步骤。','我会回到当前进度，按顺序继续。','暂时无需操作。','status'),
    'CONTRACT_REPORT_INVALID': ('这一阶段还有检查结果需要补齐。','我会补查并记录实际结果后再继续。','暂时无需操作。','review'),
    'ACPI_EVIDENCE_INVALID': ('还没核实启动文件与 A 的主板是否匹配。','我会在 Windows 中补查 A 的主板资料，再核对启动文件。','暂时无需操作。若希望 A 免装 Python，可改用多一次重启的方案。','review'),
    'EFI_DIAGNOSTICS_INVALID': ('启动 U 盘还不能保存排错记录。','我会先备份配置，开启启动日志并检查，再安排试启动。','暂时无需操作。','review'),
    'GUIDED_FAILURE': ('这一步遇到了需要排查的问题。','我会核对刚才的结果，找出下一项有用的检查。','暂时无需操作。需要现场画面时，我会说明拍哪里。','diagnose'),
    'EVIDENCE_CHANGED': ('之前保存的检查结果有缺失或变化。','我会重新核对这一步的实际结果。','暂时无需操作。','status'),
    'INTERNAL_ERROR': ('安装助手执行当前步骤时遇到了意外。','我会保留现场记录，查清原因再继续。','暂时无需操作。','diagnose')
}


def source_lock():
    return {name:source_sha(ROOT / name) for name in TRACKED} | {'workflow.json':source_sha(CONTRACT_PATH),'upgrades.json':source_sha(UPGRADE_PATH)}


def source_sha(path):
    # Only the explicit text source list uses LF identity. Evidence stays byte-exact.
    original=sha(path)
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=original['sha256']:
        raise Fault('SOURCE_CHANGED')
    data.decode('utf-8')
    return hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()


def registered_sources_match(actual, profile):
    expected=profile['sources']
    if not isinstance(actual,dict) or set(actual)!=set(expected): return False
    variants=profile.get('source_variants',{})
    return all(actual[name] in [value,*variants.get(name,[])] for name,value in expected.items())


def atomic_json(path, value):
    no_link(path.parent)
    if path.exists():
        no_link(path)
    fd, temporary = tempfile.mkstemp(prefix='.workflow-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def task_lock(run):
    no_link(run)
    path = run / '.workflow.lock'
    if path.exists():
        no_link(path)
    handle = path.open('a+b')
    try:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b'0'); handle.flush(); handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()  # OS releases the lock even after process termination.


def evidence(run, category, value):
    relative = 'evidence/' + category + '-' + uuid.uuid4().hex + '.json'
    path = run / relative
    atomic_json(path, value)
    return {'path':relative, **sha(path)}


def verify_evidence(run, proof):
    try:
        actual = sha(confined(run, proof['path']))
        if actual['sha256'] != proof['sha256'] or actual['size'] != proof['size']:
            raise ValueError()
    except (OSError, ValueError, KeyError):
        raise Fault('EVIDENCE_CHANGED') from None


def save(run, state, action):
    state['revision'] += 1
    state['updated_utc'] = utc()
    event = {'schema':'workflow-event-v1','revision':state['revision'],'at':state['updated_utc'],
             'action':action,'phase':state['phase'],'step':state['step'],'status':state['status']}
    journal = run / 'workflow-events.jsonl'
    if journal.exists():
        no_link(journal)
    with journal.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + '\n')
        handle.flush(); os.fsync(handle.fileno())
    atomic_json(run / 'workflow-state.json', state)
    # Projection for existing tools; generic checkpoint cannot grant verified on this run.
    old = read_json(run / 'state.json')
    old.update(controller='workflow-v1', phase=state['phase'], status=state['status'],
               next_action=state['step'], workflow_revision=state['revision'], machine_a=state.get('machine_a'))
    atomic_json(run / 'state.json', old)


def load(run, check_sources=True):
    try:
        no_link(run / 'workflow-state.json')
        state = read_json(run / 'workflow-state.json')
        if state['schema'] != 'workflow-state-v1' or state['phase'] not in PHASES:
            raise ValueError()
        if check_sources and state['sources'] != source_lock():
            raise Fault('SOURCE_CHANGED')
        for proof in state.get('verification_proofs', []):
            verify_evidence(run, proof)
        return state
    except (KeyError, ValueError, OSError):
        raise Fault('STATE_INVALID') from None


def initialize(run):
    if not run.exists():
        for parent in (run.parent, *run.parent.parents):
            if parent.exists():
                no_link(parent)
                break
        run.parent.mkdir(parents=True, exist_ok=True)
        init_run(run)
    no_link(run)
    with task_lock(run):
        if (run / 'workflow-state.json').exists():
            return load(run)
        legacy = read_json(run / 'state.json')
        if legacy.get('phase') != '00-remote':
            raise Fault('ACTION_NOT_ALLOWED')
        state = {'schema':'workflow-state-v1','version':VERSION,'run_id':uuid.uuid4().hex,
                 'revision':0,'phase':'00-remote','step':'prepare','status':'planned',
                 'sources':source_lock(),'source_hash_mode':'utf8-lf-v1','packet':None,'verification_proofs':[],
                 'failure':None,'attempt_signature':None,'attempt_count':0,'repair':None,
                 'machine_a':None,'created_utc':utc()}
        save(run, state, 'init')
        return state


def upgrade(run,state):
    current=source_lock()
    if state.get('version')==VERSION and state['sources']==current:
        return
    previous=state.get('version')
    profile=read_json(UPGRADE_PATH)['from'].get(previous)
    reviews=state.get('guided_reviews',[])
    if not profile or not registered_sources_match(state['sources'],profile) or state['phase'] not in profile['allowed_phases'] or state['status']=='running':
        raise Fault('UPGRADE_UNSUPPORTED')
    if state['phase'] in SOURCE_PHASES and state['step']=='repair' and not (state.get('repair') or {}).get('trial_key'):
        raise Fault('UPGRADE_UNSUPPORTED')
    allowed=set(profile.get('allowed_review_phases',[]))
    if any(r['phase'] not in allowed for r in reviews):
        raise Fault('UPGRADE_UNSUPPORTED')
    for r in reviews:
        verify_evidence(run,r['report'])
        for p in r['proofs']: verify_evidence(run,p)
    backup=evidence(run,'before-workflow-upgrade',state)
    variants=[name for name,value in state['sources'].items() if value!=profile['sources'][name]]
    state.update(version=VERSION,sources=current,source_hash_mode='utf8-lf-v1')
    if state['phase'] in profile.get('rewind_phases',[]):
        # Preserve completed work as history; supersede only the old media review.
        state.setdefault('superseded_guided_reviews',[]).extend(r for r in reviews if r['phase']=='03-media')
        state['guided_reviews']=[r for r in reviews if r['phase']!='03-media']
        state.update(phase='03-media',step='guided-contract',status='planned',failure=None)
    # Old 06/07 reviews did not enforce a per-device ledger or firmware receipt.
    if state['phase'] in ('07-boot', '08-delivery'):
        state.setdefault('superseded_guided_reviews', []).extend(
            r for r in state.get('guided_reviews', []) if r['phase'] in ('06-devices', '07-boot', '08-delivery'))
        state['guided_reviews'] = [r for r in state.get('guided_reviews', []) if r['phase'] not in ('06-devices', '07-boot', '08-delivery')]
        state.update(phase='06-devices', step='guided-contract', status='planned', failure=None)
        state['postinstall_recheck'] = True  # Reuse valid evidence; never undo disk writes.
    state.setdefault('upgrades',[]).append({'from':previous,'to':VERSION,'backup':backup,'registered_line_ending_variants':variants})
    save(run,state,f'upgrade-{previous}-to-{VERSION}')


def local_ipv4():
    # Best effort without contacting A. Unknown is reported as unknown, never fabricated.
    addresses = []
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = ipaddress.IPv4Address(item[4][0])
            if not (address.is_loopback or address.is_link_local or address.is_unspecified):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
                        candidate.bind((str(address), 0))
                    addresses.append(str(address))
                except OSError:
                    pass
    except OSError:
        pass
    return sorted(set(addresses))


def record_fault(run, state, fault):
    state['failure'] = {'code':fault.code if fault.code in ERRORS else 'INTERNAL_ERROR',
                        'details':fault.details, 'resume':state['step']}
    state['status'] = 'failed'
    if fault.code in ('PACKET_INVALID','SETUP_FAILED','FINGERPRINT_READ_FAILED','RESTART_REQUIRED'):
        state['step'] = 'import'
    save(run, state, 'failed')


def prepare(run, state, addresses=None):
    if state['phase'] != '00-remote' or state['status'] == 'running':
        raise Fault('ACTION_NOT_ALLOWED')
    state.pop('recovery_reason',None)
    addresses = local_ipv4() if addresses is None else addresses
    code = render(SOURCE.read_text(encoding='utf-8-sig'), addresses)
    relative = 'staging/ssh-setup-' + uuid.uuid4().hex[:8] + '.ps1'
    path = run / relative
    no_link(path.parent)
    with path.open('xb') as handle:
        handle.write(code.encode('utf-8-sig'))
    state.update(step='import', status='waiting_user', failure=None,
                 prepared={'path':relative, **sha(path)}, b_ipv4=addresses)
    save(run, state, 'prepare')


def import_handoff(run, state, packet_path):
    if state['phase'] != '00-remote' or state['status'] == 'running':
        raise Fault('ACTION_NOT_ALLOWED')
    text = Path(packet_path).read_text(encoding='utf-8-sig')
    state['handoff_attempted'] = True
    packet = parse_packet(text)
    if packet['status'] != 'local-ready':
        code = 'RESTART_REQUIRED' if packet['status'] == 'restart-required' else (
            'FINGERPRINT_READ_FAILED' if packet['failed_step'] == '生成连接信息' else 'SETUP_FAILED')
        raise Fault(code, {'failed_step':packet.get('failed_step')})
    # Preserve valid connection information even if only the credential/path needs correction.
    state.update(packet=packet, packet_proof=evidence(run, 'handoff', packet),
                 step='verify', status='planned', failure=None)
    try:
        secret = credential_from_bundle(text)
    except Fault:
        state['credential_import_error']=True
        raise
    if secret is not None:
        private_dir=run/'private'
        if private_dir.exists(): no_link(private_dir)
        private_dir.mkdir(mode=0o700,exist_ok=True)
        no_link(private_dir)
        target=private_dir/'a-login-password'
        if target.exists(): no_link(target)
        fd, temporary=tempfile.mkstemp(prefix='.credential-',dir=private_dir)
        try:
            with os.fdopen(fd,'w',encoding='utf-8',newline='') as handle:
                handle.write(secret)
            os.replace(temporary,target)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        state['credential_import_error']=False
    # State/evidence contain only the allowlisted packet, never the credential line.
    save(run, state, 'import')


def verify(run, state, credential_file=None, key_file=None, verifier=verify_connection):
    if state['phase'] != '00-remote' or state['step'] not in ('verify','diagnose') or state['status'] == 'running' or not state['packet']:
        raise Fault('ACTION_NOT_ALLOWED')
    if state['step'] == 'diagnose':
        raise Fault('RETRY_LIMIT')
    if credential_file is None and key_file is None:
        stored=run/'private'/'a-login-password'
        if stored.is_file() and not state.get('credential_import_error'):
            no_link(stored)
            credential_file=stored
    verify_evidence(run, state['packet_proof'])
    signature = hashlib.sha256(json.dumps(state['packet'],sort_keys=True).encode()).hexdigest()
    # A changed packet or an evidence-backed repair starts a new bounded verification cycle.
    if state['attempt_signature'] == signature and state['attempt_count'] >= 2:
        state['step'] = 'diagnose'
        raise Fault('RETRY_LIMIT')
    state['attempt_count'] = state['attempt_count'] + 1 if state['attempt_signature'] == signature else 1
    state.update(attempt_signature=signature, status='running', failure=None)
    save(run, state, 'verify-start')
    try:
        result = verifier(state['packet'], credential_file=credential_file, key_file=key_file, previous=state.get('machine_a'))
        required = PHASES['00-remote']['verification']
        if result.get('schema') != 'remote-verification-v1' or any(result.get('checks',{}).get(k) is not True for k in required):
            raise Fault('REMOTE_OUTPUT_INVALID')
        proof = evidence(run, 'remote-verification', result)
        state.update(machine_a=result['identity'], connection={'address':result['address'],'port':result['port'],'fingerprint':result['fingerprint']},
                     verification_proofs=[state['packet_proof'],proof], phase='01-hardware',step='guided-contract',status='planned',failure=None)
        save(run, state, '00-verified')
    except Fault as fault:
        if fault.code in ('CREDENTIAL_REQUIRED','CREDENTIAL_INVALID','DEPENDENCY_MISSING'):
            state['attempt_count'] = max(0,state['attempt_count']-1)
        state['step'] = 'verify'
        record_fault(run, state, fault)


def resume(run, state):
    if state['phase'] != '00-remote':
        raise Fault('ACTION_NOT_ALLOWED')
    state.update(step='verify' if state.get('packet') else 'prepare', status='planned', failure=None)
    save(run, state, 'resume')


def recheck(run, state):
    if state['phase'] != '01-hardware' or state.get('guided_reviews'):
        raise Fault('ACTION_NOT_ALLOWED')
    state.update(phase='00-remote',step='verify',status='planned',failure=None,attempt_count=0)
    save(run,state,'recheck-00')


def recover(run, state):
    if state['phase'] != '00-remote' or not state.get('failure'):
        raise Fault('ACTION_NOT_ALLOWED')
    code=state['failure']['code']
    cycles=state.setdefault('recovery_cycles',{})
    if cycles.get(code,0)>=2:
        state['step']='diagnose'
        raise Fault('RETRY_LIMIT')
    cycles[code]=cycles.get(code,0)+1
    if code=='DEPENDENCY_MISSING':
        deps=run/'runtime-deps'
        if deps.exists(): no_link(deps)
        command=[sys.executable,'-m','pip','install','--disable-pip-version-check','--target',str(deps),'paramiko==5.0.0']
        try:
            completed=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120)
            if completed.returncode:
                raise Fault('DEPENDENCY_INSTALL_FAILED',{'exit_code':completed.returncode})
        except (OSError,subprocess.TimeoutExpired):
            raise Fault('DEPENDENCY_INSTALL_FAILED') from None
        state.update(step='verify',status='planned',failure=None,attempt_count=0)
        save(run,state,'private-dependency-installed')
    elif code in ('SSH_TIMEOUT','SSH_REFUSED','SSH_UNREACHABLE','HOST_KEY_MISMATCH','SETUP_FAILED','FINGERPRINT_READ_FAILED','RESTART_REQUIRED','PACKET_INVALID'):
        # Fixed idempotent service/check script. No remote disk writes or arbitrary command.
        prepare(run,state)
        state['recovery_reason']=code
        save(run,state,'fixed-recovery-handoff')
    else:
        # Known classification has exhausted its automatic branch. Gather evidence via diagnose.
        state.update(step='diagnose',status='failed')
        save(run,state,'diagnosis-required')


SOURCE_PHASES = ('03-media', '04-install', '06-devices')

EFI_CHOICES = {
    'a': 'RapidEFI-Tool 生成后适配（推荐）',
    'b': '查找相似配置，核对差异后适配',
    'c': 'AI 按官方 Sample 与本机资料生成',
}


def has_efi_source(state):
    return any(choice['topic'] == 'efi' for choice in state.get('source_decisions', {}).get('03-media', {}).values())


def efi_choice(run, state):
    selection = state.get('efi_choice')
    if not selection or state['phase'] != '03-media':
        return None
    verify_evidence(run, selection['proof'])
    return selection['choice']


def choose_efi(run, state, choice):
    if state['phase'] != '03-media' or state['step'] != 'guided-contract' or choice not in EFI_CHOICES:
        raise Fault('ACTION_NOT_ALLOWED')
    if efi_choice(run, state) == choice:
        return
    if has_efi_source(state):
        previous = state['source_decisions']['03-media']
        archive = evidence(run, 'before-user-efi-route-change', previous)
        state.setdefault('superseded_efi_sources', []).append(archive)
        state['source_decisions']['03-media'] = {}
    proof = evidence(run, 'user-efi-choice', {'choice': choice, 'label': EFI_CHOICES[choice]})
    state['efi_choice'] = {'choice': choice, 'proof': proof}
    state.update(status='planned', failure=None)
    save(run, state, 'user-efi-choice')


def check_trial_budget(state, choice):
    key = choice['trial_key']
    if state.get('source_trials', {}).get(key, 0) < 2:
        return
    history = state.get('solution_history', {}).get(key, [])
    raise Fault('SOLUTION_RETRY_LIMIT', {'handoff': {
        'phase': state['phase'], 'topic': choice['topic'], 'target': choice['target'],
        'source': choice['source'], 'revision': choice['revision'],
        'source_evidence': choice['proofs'], 'recent_attempts': history[-2:],
        'next': '取回上述计划与结果，先核对部署回读、实际启动来源及与原始产物的差异。'
                '有新增事实时建新记录，仍无依据则交接本项并继续其他硬件。'}})


def select_source(run, state, plan_path):
    if state['phase'] not in SOURCE_PHASES or state['step'] == 'complete':
        raise Fault('ACTION_NOT_ALLOWED')
    if state['phase'] == '06-devices':
        device_record(run, state)
    route = efi_choice(run, state)
    if state['phase'] == '03-media' and route is None and not has_efi_source(state):
        raise Fault('EFI_ROUTE_REQUIRED')
    try:
        relative = Path(plan_path).absolute().relative_to(run.absolute()).as_posix()
    except ValueError:
        raise Fault('SOLUTION_REQUIRED') from None
    choice = assess_solution(run, relative, efi_route=route)
    check_trial_budget(state, choice)
    saved = state.get('source_decisions', {}).get(state['phase'], {}).get(relative)
    if saved:
        for item in saved['proofs']:
            verify_evidence(run, item)
        return saved
    state.setdefault('source_decisions', {}).setdefault(state['phase'], {})[relative] = choice
    save(run, state, 'selected-existing-source')
    return choice


def selected_solution(run, state, relative, **options):
    if not isinstance(relative, str):
        raise Fault('SOLUTION_REQUIRED')
    stored = state.get('source_decisions', {}).get(state['phase'], {}).get(relative)
    if not stored:
        raise Fault('SOLUTION_REQUIRED')
    for item in stored['proofs']:
        verify_evidence(run, item)
    return assess_solution(run, relative, efi_route=efi_choice(run, state), **options)


def diagnosis(run, state, plan_path):
    if not state.get('failure') or state['step']=='complete':
        raise Fault('ACTION_NOT_ALLOWED')
    plan = read_json(plan_path)
    required = ('hypothesis','proposed_change','target','expected_result','rollback','evidence')
    if any(not plan.get(k) for k in required) or not isinstance(plan['evidence'], list):
        raise Fault('ACTION_NOT_ALLOWED')
    proofs = []
    for relative in plan['evidence']:
        proofs.append({'path':relative, **sha(confined(run,relative))})
    if not proofs:
        raise Fault('ACTION_NOT_ALLOWED')
    # A proposal is data. It is never passed to shell/eval or auto-approved.
    choice = None
    if state['phase'] in SOURCE_PHASES:
        choice = selected_solution(run, state, plan.get('source_plan'))
        if ' '.join(str(plan['target']).casefold().split()) != ' '.join(choice['target'].casefold().split()):
            raise Fault('SOLUTION_REQUIRED', {'reason':'repair target differs from source plan'})
        check_trial_budget(state, choice)
        proofs.extend(choice['proofs'])
    state['repair'] = {'plan':evidence(run, 'repair-plan', plan),'proofs':proofs,
                       'failure_code':state['failure']['code'],'status':'proposed','phase':state['phase']}
    if choice:
        state['repair'].update(source_plan=plan['source_plan'], trial_key=choice['trial_key'])
    state.update(step='repair',status='waiting_agent')
    save(run, state, 'repair-proposed')


def repair_result(run, state, result_path):
    if state['step'] != 'repair' or not state.get('repair'):
        raise Fault('ACTION_NOT_ALLOWED')
    verify_evidence(run, state['repair']['plan'])
    if 'source_plan' in state['repair']:
        selected_solution(run, state, state['repair']['source_plan'])
    report = read_json(result_path)
    if report.get('outcome') not in ('applied','rolled-back','not-applied') or not report.get('evidence'):
        raise Fault('ACTION_NOT_ALLOWED')
    proofs = [{'path':p, **sha(confined(run,p))} for p in report['evidence']]
    # Same evidence cannot reset a retry loop over and over.
    repair_id = hashlib.sha256(json.dumps(sorted(p['sha256'] for p in proofs)).encode()).hexdigest()
    if repair_id in state.get('consumed_repairs',[]):
        raise Fault('RETRY_LIMIT')
    state.setdefault('consumed_repairs',[]).append(repair_id)
    key = state['repair'].get('trial_key')
    if key and report['outcome'] in ('applied','rolled-back'):
        attempts = state.setdefault('source_trials', {})
        attempts[key] = attempts.get(key, 0) + 1
        paths = state.setdefault('tried_source_plans', {}).setdefault(state['phase'], [])
        if state['repair']['source_plan'] not in paths:
            paths.append(state['repair']['source_plan'])
    state['repair'].update(status=report['outcome'], result=evidence(run,'repair-result',report), result_proofs=proofs)
    if key and report['outcome'] in ('applied','rolled-back'):
        history = state.setdefault('solution_history', {}).setdefault(key, [])
        history.append({'plan':state['repair']['plan'], 'result':state['repair']['result'],
                        'outcome':report['outcome'], 'evidence':proofs})
    next_step=('verify' if state.get('packet') else 'prepare') if state['phase']=='00-remote' else 'guided-contract'
    state.update(step=next_step,status='planned',failure=None,attempt_count=0)
    save(run,state,'repair-recorded-reverify-required')


def problem(run,state,report_path):
    if PHASES[state['phase']]['mode']!='guided-contract' or state['step']=='complete':
        raise Fault('ACTION_NOT_ALLOWED')
    report=read_json(report_path)
    if not re_full_code(report.get('code')) or not report.get('evidence'):
        raise Fault('CONTRACT_REPORT_INVALID')
    proofs=[{'path':p,**sha(confined(run,p))} for p in report['evidence']]
    record_fault(run,state,Fault('GUIDED_FAILURE',{'incident':report['code'],'proofs':proofs}))


def re_full_code(value):
    return isinstance(value,str) and 1<=len(value)<=60 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in value)


def device_record(run, state, closing=False):
    registered = state.get('device_audit')
    if not registered:
        raise Fault('DEVICE_AUDIT_REQUIRED')
    for ref in [registered['manifest'], *registered['proofs']]:
        verify_evidence(run, ref)
    return check_devices(run, state.get('machine_a'), registered['manifest']['path'], closing=closing)


def record_devices(run, state, path):
    if state['phase'] != '06-devices' or state['step'] != 'guided-contract':
        raise Fault('ACTION_NOT_ALLOWED')
    previous = device_record(run, state)[0] if state.get('device_audit') else None
    relative = Path(path).absolute().relative_to(run.absolute()).as_posix()
    data, proofs = check_devices(run, state.get('machine_a'), relative, previous=previous)
    if state.get('device_audit'):
        state.setdefault('device_audit_history', []).append(state['device_audit'])
    state['device_audit'] = {'manifest': proofs[0], 'proofs': proofs[1:], 'queue': device_queue(data)}
    state['verification_proofs'].extend(proofs)
    state.update(status='planned', failure=None)
    save(run, state, 'device-audit-recorded')


def boot_ready(run, state, path):
    if state['phase'] != '07-boot' or state['step'] != 'guided-contract':
        raise Fault('ACTION_NOT_ALLOWED')
    devices, _ = device_record(run, state, closing=True)
    relative = Path(path).absolute().relative_to(run.absolute()).as_posix()
    _, proofs = check_boot(run, state.get('machine_a'), relative, devices)
    state['boot_readiness'] = {'manifest': proofs[0], 'proofs': proofs[1:]}
    state['verification_proofs'].extend(proofs)
    state.update(status='waiting_user', failure=None)
    save(run, state, 'internal-boot-registered-before-reboot')


def guided_review(run, state, report_path):
    contract = PHASES[state['phase']]
    if contract['mode'] != 'guided-contract':
        raise Fault('ACTION_NOT_ALLOWED')
    report = read_json(report_path)
    if report.get('phase') != state['phase'] or set(report.get('checks',{})) != set(contract['verification']):
        raise Fault('CONTRACT_REPORT_INVALID')
    proofs = []
    if state['phase']=='03-media':
        check=report['checks']['acpi_tables']
        if check.get('result')!='pass' or not isinstance(check.get('manifest'),str):
            raise Fault('ACPI_EVIDENCE_INVALID')
        proofs.extend(check_acpi_evidence(run,state.get('machine_a'),check['manifest']))
        proofs.extend(selected_solution(run, state, report.get('source_plan'), topic='efi', require_efi=True)['proofs'])
    elif state['phase'] == '06-devices':
        devices, device_proofs = device_record(run, state, closing=True)
        proofs.extend(device_proofs)
        paths = report.get('source_plans')
        if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
            raise Fault('SOLUTION_REQUIRED')
        if not set(state.get('tried_source_plans', {}).get(state['phase'], [])) <= set(paths):
            raise Fault('SOLUTION_REQUIRED')
        reason = report.get('no_driver_changes')
        if not paths and not (isinstance(reason, str) and reason.strip()):
            raise Fault('SOLUTION_REQUIRED')
        if not paths and any(i.get('repair_attempted') is True for i in devices['items']):
            raise Fault('SOLUTION_REQUIRED')
        for path in paths:
            proofs.extend(selected_solution(run, state, path)['proofs'])
    elif state['phase'] == '07-boot':
        devices, device_proofs = device_record(run, state, closing=True)
        proofs.extend(device_proofs)
        ready = state.get('boot_readiness')
        if not ready:
            raise Fault('BOOT_REGISTRATION_REQUIRED')
        for ref in [ready['manifest'], *ready['proofs']]:
            verify_evidence(run, ref)
        _, boot_proofs = check_boot(run, state.get('machine_a'), report.get('boot_manifest'), devices, cold=True)
        before = read_json(confined(run, ready['manifest']['path']))
        after = read_json(confined(run, report['boot_manifest']))
        if any(before.get(k) != after.get(k) for k in ('esp_guid', 'entry', 'config', 'boot_order', 'boot_next')):
            raise Fault('BOOT_REGISTRATION_REQUIRED', {'reason': 'boot target changed; repeat preflight and cold tests'})
        proofs.extend(boot_proofs)
    limited = state['phase'] == '06-devices' and any(
        i['status'] == 'accepted-limit' for i in device_record(run, state)[0]['items'])
    for name in contract['verification']:
        check = report['checks'][name]
        # This validates report shape and provenance, not the semantics of Agent assertions.
        if check.get('result') not in ('pass','accepted-limit') or check.get('basis') not in ('tool','human','source-review') or not check.get('evidence'):
            raise Fault('CONTRACT_REPORT_INVALID')
        if check['result'] == 'accepted-limit':
            if state['phase'] == '07-boot' or name in ('device_audit','authorization','disk_identity','esp_identity','usb_identity','target_reidentified','backup_content','restore_sample') or not check.get('user_acceptance'):
                raise Fault('CONTRACT_REPORT_INVALID')
            limited = True
        proofs.extend({'path':p, **sha(confined(run,p))} for p in check['evidence'])
    proof = evidence(run, 'guided-review', report)
    state.setdefault('guided_reviews',[]).append({'phase':state['phase'],'meaning':'agent-and-human-reviewed; not automatically verified','limited':limited,'report':proof,'proofs':proofs})
    state['verification_proofs'].extend([proof]+proofs)
    state['failure']=None
    if contract['next']:
        state.update(phase=contract['next'],step='guided-contract',status='planned')
    else:
        state.update(step='complete',status='limited' if limited or any(r['limited'] for r in state['guided_reviews']) else 'reviewed')
    save(run,state,'guided-review')


def intro_shown(run, state):
    """Record delivery in the chat, never infer delivery from rendering output."""
    if state.get('intro_shown'):
        return
    if state['phase'] != '00-remote' or state['step'] != 'import' or not state.get('prepared'):
        raise Fault('ACTION_NOT_ALLOWED')
    state['intro_shown'] = True
    save(run, state, 'intro-shown')


SETUP_INTRO = (
    "我们先连上准备装 macOS 的电脑，看看它能装哪个版本。这一步不用插 U 盘，也不会改动分区。\n\n"
    "**先认两台电脑**\n\n"
    "- **A 电脑**　要装 macOS 的那台 Intel 或 AMD 电脑，现在运行 Windows。\n"
    "- **B 电脑**　你正在和我聊天的这台。让 A 开启远程登录（SSH），我就能从 B 检查 A 的硬件、传安装文件。\n\n"
    "**手边要有什么？**\n\n"
    "- **现在**　两台电脑接入同一个能互相访问的网络，例如家中的路由器。你能在 A 前操作，并知道 Windows 管理员账户密码（PIN 不能代替密码）。\n"
    "- **稍后**　能下载系统的网络、可以清空的 U 盘（建议 16 GB 起）、独立的备份位置，以及 A 上留给 macOS 的空间。安装时需要在 A 前看屏幕、用键鼠。\n\n"
    "**全程怎么走？**　检查硬件 → 保留 Windows，备份并留出空间 → 制作 U 盘 → 你在 A 上重启安装 → 检查驱动和硬盘启动。"
    "OpenCore 是启动菜单，第一次用它进安装程序，装好后再用它选系统。"
)

SETUP_STEPS = (
    "\n\n1. 在 **A 电脑**的开始菜单搜索 **Windows PowerShell**，右键选择 **以管理员身份运行**。\n"
    "2. 粘贴下方整段代码，按回车。两机间无法直接粘贴时，可先把代码存为文本文件传到 A。\n"
    "3. 成功后把末尾两行复制到 **B 的聊天框**，将第一行的提示换成 A 的密码或 B 上密码文件的完整路径（给过可填“已提供”）。"
    "想装的 macOS 版本也可一起写，没定就写“待推荐”。执行失败只需发回错误结果。"
)

# Human summaries at stage entry. The full checks/actions stay in the machine contract.
PHASE_CARDS = {
    '01-hardware': ('两台电脑已连通，我已确认可以读取 A 的信息和传送文件。',
                    '我会查处理器、显卡、网卡和硬盘，再告诉你适合装哪个版本、哪些功能可能用不了。', '暂时无需操作。'),
    '02-storage': ('硬件检查已有结果，开始给 Windows 和新系统安排空间。',
                   '我会核对硬盘、备份位置和可用容量，再把具体分区和大小给你看。', '看到方案后，核对要保留的数据和留给 macOS 的容量。'),
    '03-media': ('已核对备份和安装空间，开始制作 A 专用的启动 U 盘。',
                 '我会在 A 的 Windows 中准备工具并读取主板资料，制作并检查启动文件。',
                 '先备好可以清空的 U 盘。需要插入时我会提醒，清空前会请你核对是哪一只。如希望 A 免装 Python，可改用多一次重启的方案。'),
    '04-install': ('启动 U 盘已核对，接下来要在 A 的屏幕上操作。',
                   '先进入 OpenCore 启动菜单，再选 U 盘的 macOS 安装／恢复项。我会给你到桌面的操作清单。',
                   '带着 U 盘到 A 旁。文字菜单用上下键，图形菜单用左右键，回车启动；只有 Windows 时先按空格显示隐藏项。分区对不上时停在抹掉前，拍照发来。'),
    '05-macos-remote': ('A 已经进入 macOS 桌面。',
                        '打开 macOS 的远程登录后，我就能从 B 继续检查新系统。', '在 A 打开“系统设置 → 通用 → 共享”，按接下来的指引开启远程登录。'),
    '06-devices': ('已接入 A 的 macOS，开始逐项检查硬件。',
                   '我会验证显卡加速、每张网卡、无线、蓝牙、音频和 USB。某项暂时修不好，会记下来并继续查其余设备。',
                   '暂时无需操作。轮到试听、插拔设备或睡眠唤醒时，我会给你具体动作。'),
    '07-boot': ('硬件检查的结果已记录，接下来准备让 A 拔掉 U 盘也能启动。',
                '我会先核对硬盘上的启动分区、备份和 U 盘退路，再给你看要写入的位置。', '保留这只已能启动的 U 盘，等提示再拔出并测试。'),
    '08-delivery': ('安装和测试已到最后整理阶段。',
                    '我会把通过实测的功能、待处理项、备份位置和恢复步骤列在一起。', '暂时无需操作。'),
}


def display_card(heading, now, action, human, intro=None):
    blocks = [heading]
    if intro:
        blocks.append(intro)
    blocks.extend((f'**现在**　{now}', f'**接下来**　{action}', f'**请你**　{human}'))
    return '\n\n'.join(blocks)


def render_result(state, override=None):
    phase = state.get('phase','00-remote')
    contract = PHASES[phase]
    failure = override or (state.get('failure') if state.get('status') == 'failed' else None)
    result = {'schema':'workflow-output-v1','phase':phase,'step':state.get('step','init'),
              'status':state.get('status','failed'),'mode':contract['mode'],'revision':state.get('revision',0)}
    if failure:
        code = failure['code']
        summary, action, human, command = ERRORS.get(code, ERRORS['INTERNAL_ERROR'])
        automatic = code in ('DEPENDENCY_MISSING','SSH_TIMEOUT','SSH_REFUSED','SSH_UNREACHABLE','HOST_KEY_MISMATCH','FINGERPRINT_READ_FAILED','RESTART_REQUIRED')
        result.update(error=code,next_action='recover' if automatic else 'diagnose',resume_action=command,details=failure.get('details',{}))
        if code in ('CREDENTIAL_REQUIRED','CREDENTIAL_INVALID','AUTH_FAILED'):
            result.update(next_action='correct-input-then-resume')
        elif code=='PACKET_INVALID':
            result.update(next_action='correct-input-then-import')
        elif code=='CONTRACT_REPORT_INVALID':
            result.update(next_action='correct-report-then-review',contract=contract)
        elif code=='ACPI_EVIDENCE_INVALID':
            result.update(next_action='collect-acpi-then-review',contract=contract)
        elif code=='EFI_DIAGNOSTICS_INVALID':
            result.update(next_action='correct-efi-then-review',contract=contract)
        elif code=='EFI_PICKER_INVALID':
            result.update(next_action='correct-efi-then-review',contract=contract)
        elif code in ('DEVICE_AUDIT_REQUIRED','DEVICE_AUDIT_OPEN','BOOT_REGISTRATION_REQUIRED'):
            result.update(next_action=command,contract=contract)
        elif code=='SOURCE_CHANGED':
            result.update(next_action='upgrade')
        elif code in ('SOLUTION_REQUIRED', 'SOLUTION_RETRY_LIMIT'):
            result.update(next_action='lookup-then-select-source' if code == 'SOLUTION_REQUIRED' else 'new-evidence-or-handoff',contract=contract)
        elif code == 'EFI_ROUTE_REQUIRED':
            result.update(next_action='choose-efi')
    elif state['step'] in ('init', 'prepare'):
        summary, action, human = '已在这台电脑上准备好安装记录。', '我会准备给待安装电脑使用的连接代码。', '暂时无需操作。'
        result['next_action'] = 'prepare-or-import'
    elif state['step'] == 'import':
        summary = '代码会在 A 开启远程登录，设为开机自启，并允许同一局域网连接。'
        action = '收到结果后，我会连上 A，核对电脑再检查硬件。'
        human = '在 A 上运行一次代码。' + SETUP_STEPS
        result.update(next_action='import',script=state['prepared'])
        if state.get('recovery_reason')=='RESTART_REQUIRED':
            summary = 'Windows 安装远程登录功能后，提示需要重启。'
            human = '请先保存工作并重启 A。回到 Windows 后再操作。' + SETUP_STEPS
        elif state.get('recovery_reason'):
            summary = ERRORS[state['recovery_reason']][0]
            human = '在 A 重新运行检查，把新的结果发回这里。' + SETUP_STEPS
    elif state['step'] == 'verify':
        summary, action, human = '已收到 A 的连接信息。', '我会从 B 实际登录，核对电脑和账户，并试传一个文件。', '暂时无需操作。'
        result['next_action'] = 'verify'
    elif state['step'] == 'repair':
        summary, action, human = '已找到一个可尝试的修复办法。', '我会验证修复效果，再回到这一步继续。', '暂时无需操作。需要在 A 旁测试时我会说明。'
        result['next_action'] = 'repair-result'
    elif state['step'] == 'complete':
        summary = '本轮安装和验证已收尾，仍有待处理项。' if state.get('status') == 'limited' else '本轮安装和验证已收尾。'
        action, human = '我会交给你实测结果、剩余限制、备份位置和恢复方法。', '收好启动 U 盘和备份，以后需要恢复时使用。'
        result['next_action'] = 'none'
    else:
        summary, action, human = PHASE_CARDS[phase]
        reviews = state.get('guided_reviews', [])
        if reviews and reviews[-1].get('limited'):
            summary = '上一阶段的结果已记录，其中有你同意暂时保留的限制。'
        result.update(next_action='guided-contract',contract=contract)
        if phase == '06-devices':
            audit = state.get('device_audit')
            result['next_action'] = 'record-devices'
            if audit:
                queue = audit['queue']
                result['device_queue'] = queue
                summary = f"硬件与功能清单已检查 {queue['closed']}/{queue['total']} 项。"
                if queue['next_item']:
                    action = '继续处理 ' + queue['next_item'] + '，先查已维护的项目和同机实测方案。'
                elif queue['open_items']:
                    action = '可自动处理的项目已完成，我会集中给出待测和暂时受限的清单。'
                    human = '按接下来的短清单配合现场测试，或决定是否保留具体限制。'
                else:
                    result['next_action'] = 'review'
                    action = '清单已逐项收尾，审核通过后才准备硬盘引导。'
        elif phase == '07-boot':
            result['next_action'] = 'boot-ready'
            action = '我会备份并写入已验收 EFI，同时注册硬盘 OpenCore 启动项、设为优先并回读。'
            if state.get('boot_readiness'):
                result['next_action'] = 'cold-boot-then-review'
                summary = '硬盘 EFI、固件启动项与优先顺序已核对，等待拔 U 盘实测。'
                action = '确认默认进入硬盘 OpenCore，再分别冷启动 macOS 和 Windows。'
                human = '保存工作后关机、拔下 U 盘，再开机。应先看到 OpenCore 菜单；异常拍照反馈，保留 U 盘用于恢复。'
        if phase=='03-media':
            choices = state.get('source_decisions', {}).get(phase, {}).values()
            if not any(choice['topic'] == 'efi' for choice in choices):
                selection = state.get('efi_choice')
                if selection:
                    result['next_action']='lookup-then-select-source'
                    action = '已选择“' + EFI_CHOICES[selection['choice']] + '”，我会核对来源并保留原始配置。'
                    human = '暂时无需操作。轮到插 U 盘或需要你在 A 旁配合时，我会说明。'
                else:
                    result['next_action']='choose-efi'
                    summary = '备份与安装空间已确认，接下来制作适合 A 的启动文件（EFI）。'
                    action = '先选制作方式，我会核对本机资料，再制作启动 U 盘。'
                    human = '回复 a、b 或 c。已有同机成功 EFI 会保留为对照。'
    if result.get('next_action') == 'choose-efi':
        result['options'] = [{'value': key, 'label': label} for key, label in EFI_CHOICES.items()]
        human += '\n\n' + '\n'.join(key + ' · ' + label for key, label in EFI_CHOICES.items())
    if state.get('status') == 'running':
        result['next_action'] = 'resume'
        summary, action, human = '上次连接检查还没有最终结果。', '我会确认上一次检查已结束，再继续验证。', '暂时无需操作。'
    heading = f'**{phase[:2]} · {contract["title"]}**'
    result['display'] = display_card(heading, summary, action, human)
    if (result['next_action'] == 'import' and not state.get('intro_shown')
            and not state.get('packet') and not state.get('handoff_attempted') and not state.get('recovery_reason')):
        result['presentation_id'] = state['run_id'] + '/00-setup'
        result['display_compact'] = result['display']
        result['display'] = display_card(heading, summary, action, human, SETUP_INTRO)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--json', action='store_true', help='Machine output including the exact display text')
    sub = parser.add_subparsers(dest='command',required=True)
    for action in ('init','status','intro-shown','resume','recheck','recover','upgrade'):
        sub.add_parser(action)
    p = sub.add_parser('prepare'); p.add_argument('--b-ip',action='append')
    p = sub.add_parser('choose-efi'); p.add_argument('--choice',required=True,choices=EFI_CHOICES)
    p = sub.add_parser('import'); p.add_argument('--file',required=True,type=Path)
    p = sub.add_parser('verify'); group=p.add_mutually_exclusive_group(); group.add_argument('--credential-file',type=Path); group.add_argument('--key-file',type=Path)
    for action in ('diagnose','repair-result','review','problem','select-source','record-devices','boot-ready'):
        p=sub.add_parser(action); p.add_argument('--file',required=True,type=Path)
    args=parser.parse_args()
    run=args.run.absolute()
    # Optional private dependencies installed by B; never a password argument.
    deps=run/'runtime-deps'
    if deps.is_dir():
        no_link(deps); sys.path.insert(0,str(deps))
    state={'phase':'00-remote','step':'init','status':'failed'}
    fault=None
    registered=None
    try:
        if args.command=='init':
            state=initialize(run)
        else:
            with task_lock(run):
                state=load(run,check_sources=args.command!='upgrade')
                try:
                    if args.command=='upgrade': upgrade(run,state)
                    elif args.command=='intro-shown': intro_shown(run,state)
                    elif args.command=='prepare': prepare(run,state,args.b_ip)
                    elif args.command=='choose-efi': choose_efi(run,state,args.choice)
                    elif args.command=='import': import_handoff(run,state,args.file)
                    elif args.command=='verify': verify(run,state,args.credential_file,args.key_file)
                    elif args.command=='resume': resume(run,state)
                    elif args.command=='recheck': recheck(run,state)
                    elif args.command=='recover': recover(run,state)
                    elif args.command=='diagnose': diagnosis(run,state,args.file)
                    elif args.command=='repair-result': repair_result(run,state,args.file)
                    elif args.command=='review': guided_review(run,state,args.file)
                    elif args.command=='record-devices': record_devices(run,state,args.file)
                    elif args.command=='boot-ready': boot_ready(run,state,args.file)
                    elif args.command=='problem': problem(run,state,args.file)
                    elif args.command=='select-source': registered=select_source(run,state,args.file)
                except Fault as exc:
                    if exc.code in ('ACTION_NOT_ALLOWED','SOLUTION_REQUIRED','SOLUTION_RETRY_LIMIT','EFI_ROUTE_REQUIRED'):
                        fault={'code':exc.code,'details':exc.details}
                    else:
                        record_fault(run,state,exc)
                except Exception as exc:
                    record_fault(run,state,Fault('INTERNAL_ERROR',{'exception_type':type(exc).__name__}))
    except Fault as exc:
        fault={'code':exc.code}
    except Exception as exc:
        # Do not print arbitrary exception strings, arguments or remote stderr.
        fault={'code':'INTERNAL_ERROR','exception_type':type(exc).__name__}
    output=render_result(state,fault)
    if registered:
        output['selected_source'] = {k:registered[k] for k in ('topic','target','kind','source','revision')}
    if fault and fault['code']=='ACTION_NOT_ALLOWED':
        output['next_action']=render_result(state)['next_action']
    if args.json:
        print(json.dumps(output,ensure_ascii=False))
    else:
        print(output['display'])
    return 2 if fault or (state.get('status')=='failed' and not registered) else 0


if __name__=='__main__':
    raise SystemExit(main())
