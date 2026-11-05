"""Validate per-device evidence and firmware boot readiness; never mutate target A.

Evidence semantics still require Agent/human review. These gates prevent missing
rows, enumeration-only success and copy-only boot handoffs, not dishonest reports.
"""
import plistlib
import re
import uuid

from agentkit import confined, read_json, sha
from ssh_transport import Fault

CATEGORIES = ('network', 'gpu', 'wifi', 'bluetooth', 'usb', 'audio', 'storage',
              'cpu-power', 'sleep', 'continuity', 'other')
REQUIRED = set(CATEGORIES) - {'other'}
PRIORITY = {name: i for i, name in enumerate(CATEGORIES)}
CLOSED = {'passed', 'accepted-limit', 'not-applicable'}
OPEN = {'pending', 'repairing', 'waiting-user', 'deferred'}


def need(condition, code, reason):
    if not condition:
        raise Fault(code, {'reason': reason})


def text(value):
    return isinstance(value, str) and bool(value.strip())


def proof(run, path, code):
    need(text(path), code, 'evidence path required')
    try:
        result = {'path': path, **sha(confined(run, path))}
        need(result['size'] > 0, code, 'empty evidence')
        return result
    except (OSError, ValueError):
        raise Fault(code, {'reason': 'evidence file missing or outside run'}) from None


def read_manifest(run, path, schema, machine, code):
    ref = proof(run, path, code)
    try:
        value = read_json(confined(run, path))
    except (OSError, ValueError):
        raise Fault(code) from None
    need(isinstance(value, dict) and value.get('schema') == schema, code, 'manifest schema')
    need(machine and text(machine.get('uuid')) and value.get('machine_uuid') == machine['uuid'],
         code, 'target identity differs')
    return value, [ref]


def check_devices(run, machine, path, previous=None, closing=False):
    code = 'DEVICE_AUDIT_REQUIRED'
    data, proofs = read_manifest(run, path, 'device-audit-v1', machine, code)
    need(text(data.get('macos_build')), code, 'current macOS build required')
    for name in ('windows_inventory', 'macos_inventory', 'coverage_review', 'presented',
                 'rollback', 'tested_config', 'tested_efi_manifest'):
        proofs.append(proof(run, data.get(name), code))
    try:
        windows = read_json(confined(run, data['windows_inventory']))
    except (ValueError, OSError):
        raise Fault(code, {'reason': 'original Windows collector JSON required'}) from None
    need(windows.get('platform') == 'windows' and
         windows.get('host', {}).get('uuid', '').casefold() == machine['uuid'].casefold(),
         code, 'Windows inventory identity differs')
    expected = {}
    for device in windows.get('pnp', []):
        key = device.get('PNPDeviceID', '')
        kind = device.get('PNPClass')
        if kind in ('Net', 'Display') and key.upper().startswith(('PCI\\', 'USB\\')):
            expected[key.casefold()] = kind
    for device in windows.get('gpus', []):
        key = device.get('PNPDeviceID', '')
        if key.upper().startswith(('PCI\\', 'USB\\')):
            expected[key.casefold()] = 'Display'
    items = data.get('items')
    need(isinstance(items, list) and items, code, 'per-device rows required')
    ids, categories, covered = set(), set(), set()
    for item in items:
        need(isinstance(item, dict), code, 'invalid device row')
        key, kind, status = item.get('id'), item.get('category'), item.get('status')
        need(text(key) and key not in ids and kind in CATEGORIES, code, 'duplicate or invalid device')
        ids.add(key); categories.add(kind)
        windows_ids = item.get('windows_ids', [])
        need(isinstance(windows_ids, list) and all(text(w) for w in windows_ids), code, 'invalid Windows device mapping')
        if kind in ('network', 'wifi', 'gpu'):
            need(len(windows_ids) <= 1, code, 'each physical NIC/GPU needs its own row')
        for device_id in windows_ids:
            normalized = device_id.casefold()
            if normalized in expected:
                need(normalized not in covered, code, 'duplicate physical device mapping')
                need(kind in (('gpu',) if expected[normalized] == 'Display' else ('network', 'wifi')),
                     code, 'physical device mapped to wrong category')
                need(status != 'not-applicable', code, 'enumerated physical NIC/GPU must be tested or explicitly accepted')
                covered.add(normalized)
        for field in ('name', 'hardware_id', 'observed', 'driver_state'):
            need(text(item.get(field)), code, 'device identity/observation missing')
        need(status in CLOSED | OPEN, code, 'invalid device status')
        refs = item.get('evidence')
        need(isinstance(refs, list) and refs, code, 'device evidence required')
        proofs.extend(proof(run, p, code) for p in refs)
        if status == 'passed':
            test = item.get('test', {})
            need(test.get('kind') == 'functional' and test.get('basis') in ('tool', 'human')
                 and text(test.get('result')), code, 'enumeration is not a functional test')
            proofs.append(proof(run, test.get('evidence'), code))
        elif status in ('accepted-limit', 'not-applicable'):
            need(text(item.get('reason')), code, 'limitation/applicability reason required')
            proofs.append(proof(run, item.get('acceptance' if status == 'accepted-limit' else 'applicability'), code))
        else:
            need(text(item.get('next_action')), code, 'unresolved item needs a next action')
        research = item.get('research', [])
        need(isinstance(research, list), code, 'invalid research records')
        if status in ('repairing', 'deferred') or item.get('repair_attempted') is True:
            need(bool(research), code, 'look for maintained solutions before repair or deferral')
        for source in research:
            need(isinstance(source, dict) and text(source.get('url'))
                 and source['url'].startswith('https://') and text(source.get('finding')),
                 code, 'source URL and observed support/limitation required')
            proofs.append(proof(run, source.get('evidence'), code))
    need(REQUIRED <= categories, code, 'missing hardware or system-function category')
    need(set(expected) <= covered, code, 'Windows physical NIC/GPU missing from checklist')
    if previous:
        old = {i['id']: i for i in previous['items']}
        new = {i['id']: i for i in items}
        need(old.keys() <= new.keys(), code, 'previous device rows cannot disappear')
        for key in old:
            need(all(old[key][field] == new[key][field] for field in ('category', 'hardware_id')),
                 code, 'device identity cannot be relabelled')
    if closing:
        pending = [i['id'] for i in items if i['status'] not in CLOSED]
        need(not pending, 'DEVICE_AUDIT_OPEN', 'unresolved items: ' + ', '.join(pending))
    return data, proofs


def device_queue(data):
    """Do available work first; deferred/user-dependent items never starve others."""
    ordered = sorted(data['items'], key=lambda i: (PRIORITY[i['category']], i['id']))
    ready = [i for i in ordered if i['status'] in ('pending', 'repairing')]
    waiting = [i for i in ordered if i['status'] in ('waiting-user', 'deferred')]
    return {'next_item': ready[0]['id'] if ready else None,
            'open_items': [i['id'] for i in ready + waiting],
            'waiting_items': [i['id'] for i in waiting],
            'closed': len(ordered) - len(ready) - len(waiting), 'total': len(ordered)}


def check_boot(run, machine, path, devices, cold=False):
    code = 'BOOT_REGISTRATION_REQUIRED'
    data, proofs = read_manifest(run, path, 'boot-readiness-v1', machine, code)
    need(data.get('firmware_mode') == 'UEFI', code, 'this gate requires UEFI firmware evidence')
    guid = data.get('esp_guid')
    try:
        uuid.UUID(guid)
    except (ValueError, TypeError, AttributeError):
        raise Fault(code, {'reason': 'target ESP GUID required'}) from None
    for field in ('backup', 'authorization', 'readback', 'windows_preserved', 'firmware_readback', 'config'):
        proofs.append(proof(run, data.get(field), code))
    entry = data.get('entry', {})
    need(isinstance(entry, dict) and text(entry.get('id')) and re.fullmatch(r'Boot[0-9A-Fa-f]{4}', entry['id']),
         code, 'real firmware Boot#### required')
    need(entry.get('esp_guid', '').casefold().strip('{}') == guid.casefold().strip('{}')
         and entry.get('active') is True, code, 'boot entry targets wrong ESP or is inactive')
    need(entry.get('path') in ('\\EFI\\OC\\OpenCore.efi', '\\EFI\\BOOT\\BOOTx64.efi'), code, 'invalid OC loader path')
    need(data.get('variable_namespace') == 'EFI_GLOBAL_VARIABLE', code, 'OC-routed variables are not firmware BootOrder')
    order = data.get('boot_order')
    need(isinstance(order, list) and order and order[0] == entry['id'], code, 'OpenCore must be first in persistent BootOrder')
    need(data.get('boot_next') in (None, entry['id']), code, 'BootNext would bypass OpenCore')
    need(text(data.get('registration_method')), code, 'registration method required')
    try:
        actual = plistlib.loads(confined(run, data['config']).read_bytes())
        tested = plistlib.loads(confined(run, devices['tested_config']).read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        raise Fault(code, {'reason': 'invalid readback configuration'}) from None
    boot = actual.get('Misc', {}).get('Boot', {})
    need(boot.get('ShowPicker') is True and type(boot.get('Timeout')) is int and boot['Timeout'] >= 5,
         code, 'show OC picker long enough for first boot selection')
    # Boot migration may change the launcher/menu; hardware settings stay tested.
    for value in (actual, tested):
        for key in ('ShowPicker', 'Timeout', 'LauncherOption', 'LauncherPath'):
            value.get('Misc', {}).get('Boot', {}).pop(key, None)
    need(actual == tested, code, 'hardware configuration changed after device acceptance')
    if cold:
        for os_name in ('macos', 'windows'):
            result = data.get('cold_boot', {}).get(os_name, {})
            need(result.get('usb_removed') is True and result.get('success') is True,
                 code, 'both systems require USB-free cold boot evidence')
            proofs.append(proof(run, result.get('evidence'), code))
        need(data.get('cold_boot', {}).get('default_oc_observed') is True, code, 'automatic internal OC boot not observed')
        proofs.append(proof(run, data.get('cold_boot', {}).get('active_efi_evidence'), code))
    return data, proofs
