"""Offline source discovery and evidence checks. Never downloads or executes a project."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
from urllib.parse import urlsplit
from xml.parsers.expat import ExpatError

from agentkit import confined, sha
from ssh_transport import Fault


def project(repo, task):
    return {'source': 'https://github.com/' + repo, 'task': task}


GUIDE = 'https://dortania.github.io/OpenCore-Install-Guide/'
CARDS = {
    'efi': [
        project('JeoJay127/RapidEFI-Tool', '从 A 导出本工具可读的硬件报告与 ACPI。在 B 导入或在 A 的可见桌面自动配置，保留原始 EFI、configModel 与版本。'),
        project('lzhoang2801/OpCore-Simplify', '核对当前版本的硬件报告格式和目标系统。使用 A 的报告、原始表和作者入口生成独立 EFI 目录。')],
    'acpi': [project('corpnewt/SSDTTime', '输入本机原始 DSDT，选与问题对应的功能，检查生成的 AML 及需要合并的 patches_OC.plist。')],
    'usb': [project('USBToolBox/tool', '在 A 的 Windows 逐孔发现端口、记录速度和插孔，生成本机映射。'),
            project('USBToolBox/kext', '核对映射选择的运行方式、依赖与控制器匹配，再同时测试安装介质和键鼠。')],
    'gpu': [project('nullmoth/nvidia-macos-driver', 'NVIDIA 候选。按 PCI ID、显示接线、系统 build 查原作者设备表和发布资产，区分覆盖范围、历史实测和本轮回读。'),
            project('acidanthera/WhateverGreen', 'Intel／AMD 等受支持路线的补丁工具；核对具体架构、接线、已有底层驱动和作者 FAQ。')],
    'ethernet': [project('Mieze/LucyRTL8125Ethernet', 'RTL8125 候选，核对 PCI 匹配和当前 SSH 所用接口。'),
                 project('stefb69/RTL812xLucy', 'RTL8127 候选。分别核对 tag、提交对应的 CI 产物、架构、系统和铜口／光口；回读最终包的匹配字段。'),
                 project('acidanthera/IntelMausi', '仅核对作者列出的 Intel 有线设备；先比 PCI ID 再选驱动。')],
    'wifi': [project('OpenIntelWireless/itlwm', 'Intel Wi-Fi：按具体系统与芯片选择发行变体，核对配套前端、接力需求和依赖。'),
             project('acidanthera/AirportBrcmFixup', 'Broadcom 候选：根据芯片及该系统的底层驱动查适配条件。')],
    'bluetooth': [project('OpenIntelWireless/IntelBluetoothFirmware', 'Intel 蓝牙：先确认 USB 枚举及芯片标识，再按版本说明选择固件与依赖，测试扫描配对。'),
                  project('acidanthera/BrcmPatchRAM', 'Broadcom 蓝牙候选：核对 USB 标识、固件变体和系统要求。')],
    'audio': [project('acidanthera/AppleALC', '以 codec、PCB 接线及作者支持的布局为依据，分别测试播放和麦克风录音。')],
    'boot': [project('acidanthera/OpenCorePkg', '核对实际加载的 OC 构建和日志设置，取得启动证据。'),
             {'source': GUIDE + 'troubleshooting/extended/kernel-issues.html', 'task': '用确切启动阶段、panic 及平台筛选排错分支；对比同机成功安装 EFI。'}],
    'other': [{'source': GUIDE, 'task': '用板型／设备 ID、CPU 架构、系统 build、错误原文查原作者发布、维护者 issue 或可复现指南。'}]
}
KINDS = ('baseline', 'project', 'recipe')

class PlanError(ValueError):
    """Validation reason safe to return to the Agent."""


def lookup(topic, target):
    cards = list(CARDS[topic])
    if topic == 'ethernet':
        for token, index in [('8127', 1), ('8125', 0)]:
            if token in target:
                cards.insert(0, cards.pop(index))
                break
        else:
            if '8086:' in target:
                cards.insert(0, cards.pop(2))
    elif topic == 'gpu' and ('1002:' in target or '8086:' in target):
        cards.reverse()
    elif topic in ('wifi', 'bluetooth') and any(t in target.lower() for t in ('14e4:', '0a5c:', 'broadcom')):
        cards.reverse()
    template = {'topic': topic, 'target': target, 'environment': '',
                'hardware_evidence': '', 'candidates': []}
    for kind, source in [('baseline', 'local')] + [
            ('project' if c['source'].startswith('https://github.com/') else 'recipe',
             c['source']) for c in cards]:
        template['candidates'].append({'kind': kind, 'source': source, 'status': 'unchecked',
                                       'revision': '', 'fit': '', 'evidence': ''})
    if not any(row['kind'] == 'project' for row in template['candidates']):
        template['candidates'].insert(1, {'kind': 'project', 'source': '', 'status': 'unchecked',
                                           'revision': '', 'fit': '', 'evidence': ''})
    if topic == 'efi':
        for row in template['candidates']:
            row['base_config'] = ''
    return {'scope': 'offline leads; verify on A', 'topic': topic, 'cards': cards,
            'search_by': ['准确板型或 PCI/USB ID', '系统 build 与架构', '症状或错误原文'],
            'template': template}


def required_text(row, key):
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f'missing {key}')
    return value.strip()


def proof(run, path):
    file = confined(run, path)
    data = sha(file)
    if not data['size']:
        raise PlanError('empty evidence')
    return {'path': path, **data}


def is_https(source):
    url = urlsplit(source)
    return bool(url.scheme == 'https' and url.hostname and not url.username and not url.password)


def assess(run, relative, *, topic=None, require_efi=False):
    """Resolve the highest viable tier; frozen files prove provenance, not applicability."""
    try:
        proofs = [proof(run, relative)]
        if proofs[0]['size'] > 2 * 1024 * 1024:
            raise PlanError('plan exceeds 2 MiB')
        file = confined(run, relative)
        raw = file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != proofs[0]['sha256']:
            raise PlanError('plan changed while reading')
        plan = json.loads(raw.decode('utf-8-sig'))
        group = required_text(plan, 'topic')
        if group not in CARDS or (topic and group != topic):
            raise PlanError('wrong topic')
        target = required_text(plan, 'target')
        required_text(plan, 'environment')
        hw = proof(run, required_text(plan, 'hardware_evidence'))
        proofs.append(hw)
        rows = plan['candidates']
        if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
            raise PlanError('missing candidates')
        if not any(row.get('kind') == 'baseline' for row in rows):
            raise PlanError('check same-machine baseline')
        for row in rows:
            if row.get('kind') not in KINDS or row.get('status') not in ('usable', 'excluded', 'unchecked'):
                raise PlanError('unknown candidate kind or status')

        checked = set()
        for kind in KINDS:
            tier = [row for row in rows if row.get('kind') == kind]
            usable = []
            for row in tier:
                if row['status'] == 'unchecked':
                    continue
                source = required_text(row, 'source')
                if kind != 'baseline' and not is_https(source):
                    raise PlanError('use an upstream HTTPS reference')
                required_text(row, 'fit')
                proofs.append(proof(run, required_text(row, 'evidence')))
                checked.add(source.rstrip('/').casefold())
                if row['status'] == 'usable':
                    revision = required_text(row, 'revision')
                    if revision.lower() in ('main','master','head','latest','unknown','最新','未知'):
                        raise PlanError('pin release, commit or baseline snapshot')
                    usable.append(row)
            if usable:
                if kind == 'recipe' and not any(r.get('kind') == 'project' and r['status'] == 'excluded' for r in rows):
                    raise PlanError('record upstream tool or driver search before recipe fallback')
                if kind == 'recipe' and group == 'efi':
                    if any(card['source'].casefold() not in checked for card in CARDS['efi']):
                        raise PlanError('check both EFI generators before template fallback')
                row = usable[0]
                if group == 'efi':
                    confined(run, required_text(row, 'base_config'))
                if require_efi:
                    artifact = proof(run, required_text(row, 'base_config'))
                    if artifact['size'] > 16 * 1024 * 1024:
                        raise PlanError('original config.plist exceeds 16 MiB')
                    original = confined(run, artifact['path']).read_bytes()
                    if hashlib.sha256(original).hexdigest() != artifact['sha256']:
                        raise PlanError('original config.plist changed during review')
                    config = plistlib.loads(original)
                    if not isinstance(config, dict) or not all(isinstance(config.get(k), dict) for k in ('ACPI','Kernel','UEFI')):
                        raise PlanError('expected original EFI config.plist')
                    proofs.append(artifact)
                identity = [group, ' '.join(target.casefold().split()), hw['sha256'],
                            kind, row['source'].rstrip('/'), row['revision']]
                return {'kind': kind, 'source': row['source'], 'revision': row['revision'],
                        'topic': group, 'target': target, 'proofs': proofs,
                        'trial_key': hashlib.sha256(json.dumps(identity).encode()).hexdigest()}
            if any(r['status'] == 'unchecked' for r in tier):
                raise PlanError('check the higher-priority candidates first')
        raise PlanError('no applicable source; collect evidence or hand off')
    except PlanError as exc:
        raise Fault('SOLUTION_REQUIRED', {'reason': str(exc)}) from exc
    except (OSError, KeyError, TypeError, ValueError, AttributeError, OverflowError, ExpatError, plistlib.InvalidFileException) as exc:
        raise Fault('SOLUTION_REQUIRED', {'reason': 'check plan, plist and evidence files inside run'}) from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    find = subs.add_parser('lookup')
    find.add_argument('topic', choices=sorted(CARDS))
    find.add_argument('--target', required=True, help='Stable board or device identifier')
    check = subs.add_parser('check')
    check.add_argument('--run', required=True, type=Path)
    check.add_argument('--file', required=True, help='Private plan path relative to run')
    args = parser.parse_args()
    if args.command == 'lookup':
        result = lookup(args.topic, args.target)
    else:
        try:
            result = assess(args.run, args.file)
        except Fault as exc:
            print(json.dumps({'next': 'research-or-handoff', 'error': exc.code, **exc.details}, ensure_ascii=False))
            return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
