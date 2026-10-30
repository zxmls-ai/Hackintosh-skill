"""Pinned SSH verification. Fixed read-only probe and one temporary SFTP round trip."""
import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import time
import queue
import threading
import uuid

CREDENTIAL_MARKER = 'A_LOGIN_CREDENTIAL: '
CREDENTIAL_PLACEHOLDER = '请将此字段替换为 A 电脑的登录密码，或 B 电脑上包含登录密码的文件完整路径；已提供可填“已提供”'


class Fault(Exception):
    def __init__(self, code, details=None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


def parse_packet(text):
    lines = [line.strip() for line in text.lstrip('\ufeff').splitlines() if line.strip().startswith('SSH_HANDOFF_V1 ')]
    if len(lines) != 1:
        raise Fault('PACKET_INVALID')
    try:
        raw = json.loads(lines[0].split(' ', 1)[1])
        if raw['schema'] != 'ssh-handoff-v1' or raw['stage'] != '00':
            raise ValueError()
        status = raw['status']
        if status in ('failed', 'restart-required'):
            # Never copy arbitrary raw output (which may include credentials) into controller logs.
            step = raw.get('failed_step', '')
            known_steps = {'权限检查','安装服务器','启动并检查监听','配置防火墙','生成连接信息'}
            return {'schema':raw['schema'], 'stage':'00', 'status':status,
                    'failed_step':step if step in known_steps else '未知步骤'}
        if status != 'local-ready':
            raise ValueError()
        host, user = raw['host'], raw['user']
        if not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,63}', host):
            raise ValueError()
        if not isinstance(user, str) or not user.strip() or len(user) > 256 or any(ord(c) < 32 for c in user):
            raise ValueError()
        port = raw['port']
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError()
        addresses = []
        for entry in raw['ipv4']:
            address = ipaddress.IPv4Address(entry['ip'])
            if address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast:
                raise ValueError()
            if str(address) not in addresses:
                addresses.append(str(address))
        if not 1 <= len(addresses) <= 8:
            raise ValueError()
        keys = raw['host_keys']
        if not 1 <= len(keys) <= 8 or any(not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}', k['sha256']) for k in keys):
            raise ValueError()
        checks = raw['checks']
        if checks.get('service') != 'Running' or checks.get('startup') != 'Auto':
            raise ValueError()
        return {'schema':raw['schema'], 'stage':'00', 'status':status, 'host':host,
                'user':user, 'port':port, 'addresses':addresses,
                'fingerprints':sorted(set(k['sha256'] for k in keys))}
    except (KeyError, ValueError, TypeError, AttributeError):
        raise Fault('PACKET_INVALID') from None


def key_fingerprint(key):
    return 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')


def read_secret(path):
    # The path, never its contents, may be passed in process arguments.
    try:
        content = Path(path).read_bytes()
        value = content.decode('utf-16' if content.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig').rstrip('\r\n')
    except (OSError, UnicodeError):
        raise Fault('CREDENTIAL_INVALID') from None
    if '\n' in value or '\r' in value:
        matches = re.findall(r'^(?:密码|登录密码|Windows登录密码|password)[ \t]*[:：=][ \t]?(.*)$', value, re.MULTILINE | re.IGNORECASE)
        if len(matches) != 1:
            raise Fault('CREDENTIAL_INVALID')
        value = matches[0].rstrip('\r')
    if not value or '\n' in value or '\r' in value or '\0' in value:
        raise Fault('CREDENTIAL_INVALID')
    return value


def credential_from_bundle(text):
    """Return a secret only to the caller's credential store, never to parsed packet/state."""
    values = [line[len(CREDENTIAL_MARKER):] for line in text.lstrip('\ufeff').splitlines() if line.startswith(CREDENTIAL_MARKER)]
    if not values:
        return None  # Legacy packets remain usable with previously supplied credentials.
    if len(values) != 1:
        raise Fault('CREDENTIAL_INVALID')
    value = values[0]
    if not value or value == CREDENTIAL_PLACEHOLDER or value.strip('“”"') == '已提供':
        return None
    if value.startswith('密码='):
        value = value[len('密码='):]
    else:
        candidate = value[1:-1] if len(value)>1 and value[0]==value[-1] and value[0] in ('"',"'") else value
        is_file = candidate.startswith('文件=')
        if is_file:
            candidate = candidate[len('文件='):]
        if is_file or Path(candidate).is_absolute() or re.match(r'^[A-Za-z]:[\\/]',candidate):
            return read_secret(candidate)
    if not value or '\0' in value:
        raise Fault('CREDENTIAL_INVALID')
    return value


def probe_command():
    source = Path(__file__).with_name('probe-windows.ps1').read_text(encoding='utf-8-sig')
    encoded = base64.b64encode(source.encode('utf-16-le')).decode('ascii')
    return 'powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand ' + encoded


def read_channel(channel, timeout=25):
    deadline = time.monotonic() + timeout
    out, err = bytearray(), bytearray()
    while True:
        while channel.recv_ready():
            out.extend(channel.recv(65536))
            if len(out) > 1048576:
                raise Fault('REMOTE_OUTPUT_INVALID')
        while channel.recv_stderr_ready():
            err.extend(channel.recv_stderr(65536))
            if len(err) > 1048576:
                raise Fault('REMOTE_OUTPUT_INVALID')
        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
            break
        if time.monotonic() >= deadline:
            raise Fault('REMOTE_COMMAND_TIMEOUT')
        time.sleep(0.02)
    if channel.recv_exit_status() != 0:
        raise Fault('REMOTE_PROBE_FAILED')
    return bytes(out).decode('utf-8-sig', errors='replace')


def validate_identity(text, expected, previous=None):
    try:
        lines = [s for s in text.splitlines() if s.startswith('WINDOWS_SSH_PROBE_V1 ')]
        if len(lines) != 1:
            raise ValueError()
        raw = json.loads(lines[0].split(' ', 1)[1])
        if raw['schema'] != 'windows-ssh-probe-v1' or raw['os'] != 'Windows':
            raise ValueError()
        if raw['host'].casefold() != expected['host'].casefold() or raw['user'].casefold() != expected['user'].casefold():
            raise Fault('IDENTITY_MISMATCH')
        machine_id = str(uuid.UUID(raw['uuid'])).lower()
        if machine_id in ('00000000-0000-0000-0000-000000000000','ffffffff-ffff-ffff-ffff-ffffffffffff'):
            raise Fault('IDENTITY_INCOMPLETE')
        if previous and previous['uuid'] != machine_id:
            raise Fault('IDENTITY_MISMATCH')
        if raw['admin'] is not True:
            raise Fault('ADMIN_REQUIRED')
        temp = raw['temp']
        if not isinstance(temp, str) or not re.match(r'^[A-Za-z]:[\\/]', temp) or '..' in temp.replace('\\','/').split('/') or any(ord(c)<32 for c in temp):
            raise ValueError()
        return {'host':raw['host'], 'user':raw['user'], 'uuid':machine_id, 'os':'Windows', 'admin':True, 'temp':temp}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise Fault('REMOTE_OUTPUT_INVALID') from None


def sftp_roundtrip(client, temp):
    sftp = None
    created = False
    cleanup_failed = False
    remote = temp.replace('\\', '/').rstrip('/') + '/hackintosh-probe-' + uuid.uuid4().hex + '.txt'
    payload = ('hackintosh-ssh-check-' + uuid.uuid4().hex).encode('ascii')
    try:
        sftp = client.open_sftp()
        sftp.get_channel().settimeout(15)
        with sftp.open(remote, 'wx') as handle:
            created = True
            handle.write(payload)
        with sftp.open(remote, 'rb') as handle:
            if handle.read(len(payload) + 1) != payload:
                raise Fault('SFTP_FAILED')
    except Fault:
        raise
    except Exception:
        raise Fault('SFTP_FAILED') from None
    finally:
        if sftp:
            if created:
                try:
                    sftp.remove(remote)
                except Exception:
                    cleanup_failed = True
            sftp.close()
        if cleanup_failed:
            raise Fault('SFTP_CLEANUP_FAILED', {'temporary_file':remote})


def verify_connection(packet, credential_file=None, key_file=None, previous=None, timeout=5):
    try:
        import paramiko
    except ImportError:
        raise Fault('DEPENDENCY_MISSING') from None
    if bool(credential_file) == bool(key_file):
        raise Fault('CREDENTIAL_REQUIRED')
    # Password loading does not authenticate; the policy runs before Paramiko auth.
    password = read_secret(credential_file) if credential_file else None
    attempts = []
    class PinPolicy(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            observed = key_fingerprint(key)
            if observed not in packet['fingerprints']:
                raise Fault('HOST_KEY_MISMATCH', {'observed_fingerprint':observed})
    for address in packet['addresses']:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(PinPolicy())
        try:
            client.connect(address, port=packet['port'], username=packet['user'], password=password,
                           key_filename=str(key_file) if key_file else None, allow_agent=False,
                           look_for_keys=False, timeout=timeout, banner_timeout=timeout,
                           auth_timeout=timeout, channel_timeout=timeout)
            transport = client.get_transport()
            fingerprint = key_fingerprint(transport.get_remote_server_key())
            result_queue = queue.Queue(maxsize=1)
            def inspect_session():
                try:
                    channel = transport.open_session(timeout=timeout)
                    try:
                        channel.exec_command(probe_command())
                        found = validate_identity(read_channel(channel), packet, previous)
                    finally:
                        channel.close()
                    sftp_roundtrip(client, found['temp'])
                    result_queue.put((True, found))
                except Exception as exc:
                    result_queue.put((False, exc))
            # Covers SSH exec/subsystem acknowledgements, which can block before reads begin.
            worker = threading.Thread(target=inspect_session, daemon=True)
            worker.start()
            try:
                ok, identity = result_queue.get(timeout=45)
            except queue.Empty:
                raise Fault('REMOTE_COMMAND_TIMEOUT') from None
            if not ok:
                if isinstance(identity, Fault):
                    raise identity
                raise Fault('REMOTE_PROBE_FAILED')
            identity.pop('temp')
            return {'schema':'remote-verification-v1', 'address':address, 'port':packet['port'],
                    'fingerprint':fingerprint, 'identity':identity,
                    'checks':{'ssh':True,'host_key':True,'identity':True,'admin':True,'sftp':True},
                    'attempts':attempts}
        except Fault:
            raise
        except paramiko.AuthenticationException:
            # Do not repeat a failed password across interfaces or guess another account.
            raise Fault('AUTH_FAILED') from None
        except paramiko.ssh_exception.NoValidConnectionsError as exc:
            errors = list(exc.errors.values())
            code = 'SSH_REFUSED' if errors and all(isinstance(e, ConnectionRefusedError) for e in errors) else 'SSH_UNREACHABLE'
            attempts.append({'address':address,'code':code})
        except (socket.timeout, TimeoutError):
            attempts.append({'address':address,'code':'SSH_TIMEOUT'})
        except paramiko.SSHException:
            raise Fault('SSH_PROTOCOL_FAILED') from None
        except OSError:
            attempts.append({'address':address,'code':'SSH_UNREACHABLE'})
        finally:
            client.close()
    codes = {a['code'] for a in attempts}
    raise Fault(next(iter(codes)) if len(codes) == 1 else 'SSH_UNREACHABLE', {'attempts':attempts})
