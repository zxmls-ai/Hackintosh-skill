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
from ssh_transport import Fault, parse_packet, verify_connection

VERSION = '0.2.0'
ROOT = Path(__file__).resolve().parent
CONTRACT_PATH = ROOT.parent / 'workflow.json'
CONTRACT = read_json(CONTRACT_PATH)
PHASES = {p['id']:p for p in CONTRACT['phases']}
TRACKED = ['workflow.py','ssh_transport.py','probe-windows.ps1','enable-windows-ssh.ps1','prepare_ssh_handoff.py','agentkit.py']

# code -> summary, diagnostic action, human input, fixed resume action
ERRORS = {
    'PACKET_INVALID': ('连接结果格式不完整','重新读取原始回传；不要补写缺失字段','重新粘贴完整 SSH_HANDOFF_V1 结果','import'),
    'SETUP_FAILED': ('A 端配置未完成','检查失败步骤与原始错误，按已知规则处理','按当前错误提示提供一次检查结果','prepare'),
    'FINGERPRINT_READ_FAILED': ('公钥指纹采集失败','对比实际收到的脚本与模板，检查公钥读取；不重装 SSH','运行修正后的整块代码并回传结果','prepare'),
    'RESTART_REQUIRED': ('A 端组件安装需要重启','保存现场；重启后重新运行配置脚本','保存工作后重启 A，回传新的连接结果','prepare'),
    'DEPENDENCY_MISSING': ('B 缺少 SSH 库','Agent 在任务目录安装 Paramiko 后重试，不改 A','无需操作','verify'),
    'DEPENDENCY_INSTALL_FAILED': ('B 的 SSH 库安装未完成','核对 B 的 Python、网络与包源，保持原任务','暂时无需操作','diagnose'),
    'CREDENTIAL_REQUIRED': ('尚未取得登录凭据','使用已提供的凭据；未提供才询问一次','提供账户密码的取得方式；已有密钥可沿用','verify'),
    'CREDENTIAL_INVALID': ('凭据文件不可用','检查读取方式，不把 PIN 当作账户密码','仅在确实缺少时补充账户凭据','verify'),
    'SSH_TIMEOUT': ('SSH 连接超时','核对回传地址、B 到 A 链路、监听和有效防火墙；不重装','检查仍无法完成时，在 A 运行整块检查并回传一次','verify'),
    'SSH_REFUSED': ('A 拒绝 SSH 连接','核对实际监听与服务状态；已装服务不叠装','在 A 运行整块检查并回传一次','verify'),
    'SSH_UNREACHABLE': ('无法访问回传的 A 地址','核对地址与路由；只尝试回传候选，不扫描全网','必要时回传 A 的最新检查结果','verify'),
    'AUTH_FAILED': ('SSH 身份认证失败','核对真实用户名、密码类型与认证策略；停止重复密码尝试','核对一次账户凭据，不必改成公钥','verify'),
    'HOST_KEY_MISMATCH': ('主机指纹与回传不符','停止发送凭据，核对 IP、系统重装和新的 A 端公钥','从 A 回传最新连接结果','import'),
    'IDENTITY_MISMATCH': ('连接后的机器或账户身份不符','停止后续操作，重新确认目标电脑','确认目标 A，提供其连接结果','import'),
    'IDENTITY_INCOMPLETE': ('无法取得可靠机器标识','进入专项核对，保留主机密钥和硬件证据','按诊断结果补充身份资料','verify'),
    'ADMIN_REQUIRED': ('远程会话没有管理员权限','检查实际账户与远程令牌，不通过关闭账户保护绕过','按诊断结果使用获授权的管理员账户','verify'),
    'SSH_PROTOCOL_FAILED': ('SSH 协议协商未通过','检查服务类型、版本和日志，不关闭指纹验证','必要时提供 A 的检查结果','verify'),
    'REMOTE_COMMAND_TIMEOUT': ('远程只读检查超时','核对服务会话与 PowerShell 响应','暂时无需操作','verify'),
    'REMOTE_PROBE_FAILED': ('远程只读检查失败','检查 PowerShell、CIM 与执行环境','必要时回传 A 的指定只读检查结果','verify'),
    'REMOTE_OUTPUT_INVALID': ('远程检查结果不能验证','检查输出编码与固定探针，不补写成功结果','暂时无需操作','verify'),
    'SFTP_FAILED': ('文件传输验证失败','检查 SFTP 子系统和账户临时目录权限','暂时无需操作','verify'),
    'SFTP_CLEANUP_FAILED': ('测试文件清理未完成','核对并仅清理本次记录的临时测试文件','暂时无需操作','verify'),
    'RETRY_LIMIT': ('相同条件下验证已连续失败','收集新证据并形成诊断方案，禁止无限重试','仅补充当前诊断所需的一项反馈','diagnose'),
    'SOURCE_CHANGED': ('执行程序或流程规则已改变','保留任务记录，核对版本变更；不要静默换脚本','暂时无需操作','status'),
    'RESUME_REQUIRED': ('有中断的操作需要恢复','核对现场后重跑当前步骤，不跳到下一阶段','无需操作','resume'),
    'STATE_INVALID': ('任务状态不完整','保留原文件，检查最后一条记录，不重新建同名任务','暂时无需操作','status'),
    'ACTION_NOT_ALLOWED': ('当前步骤不接受此操作','读取 status 的 next_action 并按顺序执行','无需操作','status'),
    'CONTRACT_REPORT_INVALID': ('阶段报告不符合当前合同','按返回的检查项补全真实证据后重交 review；不要伪造通过','无需操作','review'),
    'GUIDED_FAILURE': ('当前阶段遇到需要诊断的问题','按当前阶段收集证据，提交诊断方案','仅在确需现场信息时反馈','diagnose'),
    'EVIDENCE_CHANGED': ('验收证据已变化或缺失','重新核对当前步骤；原完成状态不可沿用','暂时无需操作','status'),
    'INTERNAL_ERROR': ('遇到未覆盖的执行错误','记录错误类别与复现条件，进入标准诊断流程','暂时无需操作','diagnose')
}


def source_lock():
    return {name:sha(ROOT / name)['sha256'] for name in TRACKED} | {'workflow.json':sha(CONTRACT_PATH)['sha256']}


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
                 'sources':source_lock(),'packet':None,'verification_proofs':[],
                 'failure':None,'attempt_signature':None,'attempt_count':0,'repair':None,
                 'machine_a':None,'created_utc':utc()}
        save(run, state, 'init')
        return state


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
    packet = parse_packet(Path(packet_path).read_text(encoding='utf-8-sig'))
    if packet['status'] != 'local-ready':
        code = 'RESTART_REQUIRED' if packet['status'] == 'restart-required' else (
            'FINGERPRINT_READ_FAILED' if packet['failed_step'] == '生成连接信息' else 'SETUP_FAILED')
        raise Fault(code, {'failed_step':packet.get('failed_step')})
    # Import stores only the allowlisted packet, never the user's surrounding chat.
    state.update(packet=packet, packet_proof=evidence(run, 'handoff', packet),
                 step='verify', status='planned', failure=None)
    save(run, state, 'import')


def verify(run, state, credential_file=None, key_file=None, verifier=verify_connection):
    if state['phase'] != '00-remote' or state['step'] not in ('verify','diagnose') or state['status'] == 'running' or not state['packet']:
        raise Fault('ACTION_NOT_ALLOWED')
    if state['step'] == 'diagnose':
        raise Fault('RETRY_LIMIT')
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
    state['repair'] = {'plan':evidence(run, 'repair-plan', plan),'proofs':proofs,
                       'failure_code':state['failure']['code'],'status':'proposed','phase':state['phase']}
    state.update(step='repair',status='waiting_agent')
    save(run, state, 'repair-proposed')


def repair_result(run, state, result_path):
    if state['step'] != 'repair' or not state.get('repair'):
        raise Fault('ACTION_NOT_ALLOWED')
    verify_evidence(run, state['repair']['plan'])
    report = read_json(result_path)
    if report.get('outcome') not in ('applied','rolled-back','not-applied') or not report.get('evidence'):
        raise Fault('ACTION_NOT_ALLOWED')
    proofs = [{'path':p, **sha(confined(run,p))} for p in report['evidence']]
    # Same evidence cannot reset a retry loop over and over.
    repair_id = hashlib.sha256(json.dumps(sorted(p['sha256'] for p in proofs)).encode()).hexdigest()
    if repair_id in state.get('consumed_repairs',[]):
        raise Fault('RETRY_LIMIT')
    state.setdefault('consumed_repairs',[]).append(repair_id)
    state['repair'].update(status=report['outcome'], result=evidence(run,'repair-result',report), result_proofs=proofs)
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


def guided_review(run, state, report_path):
    contract = PHASES[state['phase']]
    if contract['mode'] != 'guided-contract':
        raise Fault('ACTION_NOT_ALLOWED')
    report = read_json(report_path)
    if report.get('phase') != state['phase'] or set(report.get('checks',{})) != set(contract['verification']):
        raise Fault('CONTRACT_REPORT_INVALID')
    proofs = []
    limited = False
    for name in contract['verification']:
        check = report['checks'][name]
        # This validates report shape and provenance, not the semantics of Agent assertions.
        if check.get('result') not in ('pass','accepted-limit') or check.get('basis') not in ('tool','human','source-review') or not check.get('evidence'):
            raise Fault('CONTRACT_REPORT_INVALID')
        if check['result'] == 'accepted-limit':
            if name in ('authorization','disk_identity','esp_identity','usb_identity','target_reidentified','backup_content','restore_sample') or not check.get('user_acceptance'):
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


def render_result(state, override=None):
    phase = state.get('phase','00-remote')
    contract = PHASES[phase]
    failure = override or (state.get('failure') if state.get('status') == 'failed' else None)
    result = {'schema':'workflow-output-v1','phase':phase,'step':state.get('step','init'),
              'status':state.get('status','failed'),'mode':contract['mode'],'revision':state.get('revision',0)}
    if failure:
        code = failure['code']
        summary, action, human, command = ERRORS.get(code, ERRORS['INTERNAL_ERROR'])
        lines = [f'进度：{phase[:2]} {contract["title"]}｜异常 {code}：{summary}',f'下一步：{action}',f'需要你：{human}']
        automatic = code in ('DEPENDENCY_MISSING','SSH_TIMEOUT','SSH_REFUSED','SSH_UNREACHABLE','HOST_KEY_MISMATCH','FINGERPRINT_READ_FAILED','RESTART_REQUIRED')
        result.update(error=code,next_action='recover' if automatic else 'diagnose',resume_action=command,details=failure.get('details',{}))
        if code in ('CREDENTIAL_REQUIRED','CREDENTIAL_INVALID','AUTH_FAILED'):
            result.update(next_action='correct-input-then-resume')
        elif code=='PACKET_INVALID':
            result.update(next_action='correct-input-then-import')
        elif code=='CONTRACT_REPORT_INVALID':
            result.update(next_action='correct-report-then-review',contract=contract)
    elif state['step'] == 'prepare':
        lines = ['进度：00 远程接入｜任务已建立','下一步：自动生成 A 端配置代码；已有连接结果可直接导入','需要你：暂时无需操作']
        result['next_action'] = 'prepare-or-import'
    elif state['step'] == 'import':
        lines = ['进度：00 远程接入｜A 端固定配置代码已准备','下一步：配置并采集 A 的连接信息',
                 '需要你：确认有账户密码（不是 PIN）；在 A 的管理员 PowerShell 粘贴下方代码，回传整行结果。尚未提供时补充密码取得方式和目标 macOS 版本']
        result.update(next_action='import',script=state['prepared'])
        if state.get('recovery_reason')=='RESTART_REQUIRED':
            lines=['进度：00 远程接入｜A 的 SSH 组件要求重启','下一步：重启后继续本机配置与检查',
                   '需要你：保存工作并重启 A；在管理员 PowerShell 运行下方代码，回传整行结果']
    elif state['step'] == 'verify':
        lines = ['进度：00 远程接入｜连接信息已接收','下一步：自动验证 SSH、身份、权限和文件传输','需要你：已有凭据则无需操作；未提供时补充账户密码取得方式']
        result['next_action'] = 'verify'
    elif state['step'] == 'repair':
        lines = [f'进度：{phase[:2]} {contract["title"]}｜修复方案已记录，尚未认定故障解决','下一步：按授权范围处理，提交结果后重跑当前阶段验收','需要你：仅在方案确实需要现场操作或新授权时参与']
        result['next_action'] = 'repair-result'
    elif state['step'] == 'complete':
        lines = ['进度：08 交付｜流程记录已完成','下一步：交付实测配置、恢复方法及未解决限制','需要你：无需操作']
        result['next_action'] = 'none'
    else:
        summary = '00 接入验证通过' if phase == '01-hardware' else '上一阶段检查记录已接收'
        lines = [f'进度：{phase[:2]} {contract["title"]}｜{summary}',f'下一步：按本阶段合同执行：{contract["actions"][0]}','需要你：自动检查先继续，仅收集本阶段确实缺少的信息']
        result.update(next_action='guided-contract',contract=contract)
    if state.get('status') == 'running':
        result['next_action'] = 'resume'
        lines = ['进度：00 远程接入｜上次验证未结束，结果尚未确认','下一步：确认旧进程结束后运行 resume，重跑验收','需要你：无需操作']
    result['display'] = '\n'.join(lines)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--json', action='store_true', help='Machine output including the exact display text')
    sub = parser.add_subparsers(dest='command',required=True)
    for action in ('init','status','resume','recheck','recover'):
        sub.add_parser(action)
    p = sub.add_parser('prepare'); p.add_argument('--b-ip',action='append')
    p = sub.add_parser('import'); p.add_argument('--file',required=True,type=Path)
    p = sub.add_parser('verify'); group=p.add_mutually_exclusive_group(); group.add_argument('--credential-file',type=Path); group.add_argument('--key-file',type=Path)
    for action in ('diagnose','repair-result','review','problem'):
        p=sub.add_parser(action); p.add_argument('--file',required=True,type=Path)
    args=parser.parse_args()
    run=args.run.absolute()
    # Optional private dependencies installed by B; never a password argument.
    deps=run/'runtime-deps'
    if deps.is_dir():
        no_link(deps); sys.path.insert(0,str(deps))
    state={'phase':'00-remote','step':'init','status':'failed'}
    fault=None
    try:
        if args.command=='init':
            state=initialize(run)
        else:
            with task_lock(run):
                state=load(run)
                try:
                    if args.command=='prepare': prepare(run,state,args.b_ip)
                    elif args.command=='import': import_handoff(run,state,args.file)
                    elif args.command=='verify': verify(run,state,args.credential_file,args.key_file)
                    elif args.command=='resume': resume(run,state)
                    elif args.command=='recheck': recheck(run,state)
                    elif args.command=='recover': recover(run,state)
                    elif args.command=='diagnose': diagnosis(run,state,args.file)
                    elif args.command=='repair-result': repair_result(run,state,args.file)
                    elif args.command=='review': guided_review(run,state,args.file)
                    elif args.command=='problem': problem(run,state,args.file)
                except Fault as exc:
                    if exc.code=='ACTION_NOT_ALLOWED':
                        fault={'code':exc.code}
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
    if fault and fault['code']=='ACTION_NOT_ALLOWED':
        output['next_action']=render_result(state)['next_action']
    if args.json:
        print(json.dumps(output,ensure_ascii=False))
    else:
        print(output['display'])
    return 2 if fault or state.get('status')=='failed' else 0


if __name__=='__main__':
    raise SystemExit(main())
