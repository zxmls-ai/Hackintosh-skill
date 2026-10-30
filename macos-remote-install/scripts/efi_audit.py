"""Read-only EFI inventory/diff. Static evidence only; never infers boot success."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import sys

from agentkit import confined, files, no_link, sha, utc, write_new

CORE = ('BOOT/BOOTx64.efi', 'OC/OpenCore.efi', 'OC/Drivers/OpenRuntime.efi')
LISTS = (('ACPI', 'Add', 'Path', 'OC/ACPI/'),
         ('ACPI', 'Delete', None, None), ('ACPI', 'Patch', None, None),
         ('Kernel', 'Add', 'BundlePath', 'OC/Kexts/'),
         ('Kernel', 'Block', None, None), ('Kernel', 'Patch', None, None),
         ('UEFI', 'Drivers', 'Path', 'OC/Drivers/'))


def snapshot(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in files(root)}


def changes(before, after, path=''):
    """Paths only: do not serialize serial numbers, ROMs or other setting values."""
    if type(before) is not type(after):
        return [path or '/']
    if isinstance(before, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            if key == 'Comment':
                continue
            child = path + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in before or key not in after:
                result.append(child)
            else:
                result.extend(changes(before[key], after[key], child))
        return result
    if isinstance(before, list):
        result = []
        for index in range(max(len(before), len(after))):
            child = path + '/' + str(index)
            if index >= len(before) or index >= len(after):
                result.append(child)
            else:
                result.extend(changes(before[index], after[index], child))
        return result
    return [] if before == after else [path or '/']


def file_ref(root, manifest, relative):
    confined(root, relative)  # Reject traversal even when the file is missing.
    return {'path': relative, 'present': relative in manifest,
            'sha256': manifest.get(relative, {}).get('sha256')}


def inventory(root):
    root = Path(root).absolute()
    no_link(root)
    manifest = snapshot(root)
    raw = (root / 'OC/config.plist').read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['OC/config.plist']['sha256']:
        raise ValueError('Configuration changed during inspection')
    config = plistlib.loads(raw)
    if not isinstance(config, dict):
        raise ValueError('Expected a configuration dictionary')
    entries = []
    for section, key, path_key, prefix in LISTS:
        rows = config.get(section, {}).get(key, [])
        if not isinstance(rows, list):
            raise ValueError('Expected an ordered array: ' + section + '/' + key)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError('Unsupported legacy/non-dictionary entry; use matching OC documentation')
            flag = row.get('Enabled')
            conditions = {name: row[name] for name in ('Arch', 'MinKernel', 'MaxKernel') if row.get(name)}
            conditional = any(value and (name != 'Arch' or value != 'Any') for name, value in conditions.items())
            status = ('disabled' if flag is False else
                      'enabled-conditional' if flag is True and conditional else
                      'enabled-configured' if flag is True else 'invalid-enabled-flag')
            entry = {'section': section + '/' + key, 'index': index,
                     'status': status, 'conditions': conditions, 'runtime_loaded': 'unknown'}
            if path_key:
                name = row.get(path_key)
                if not isinstance(name, str) or not name:
                    raise ValueError('Missing entry path')
                entry['path'] = name
                if section == 'Kernel':
                    base = prefix + name
                    confined(root, base)
                    entry['bundle_files_present'] = any(p.startswith(base + '/') for p in manifest)
                    entry['references'] = []
                    for ref_key in ('PlistPath', 'ExecutablePath'):
                        if row.get(ref_key):
                            entry['references'].append(file_ref(root, manifest, base + '/' + row[ref_key]))
                    info_rel = base + '/' + row.get('PlistPath', 'Contents/Info.plist')
                    if info_rel in manifest:
                        try:
                            info = plistlib.loads(confined(root, info_rel).read_bytes())
                            entry['bundle_version_declared'] = info.get('CFBundleVersion')
                            entry['bundle_id_declared'] = info.get('CFBundleIdentifier')
                        except (plistlib.InvalidFileException, ValueError, AttributeError):
                            entry['info_error'] = 'unreadable-plist'
                else:
                    entry['references'] = [file_ref(root, manifest, prefix + name)]
            entries.append(entry)
    if snapshot(root) != manifest:
        raise ValueError('EFI changed during inspection; copy a stable snapshot and retry')
    report = {'config_sha256': manifest['OC/config.plist']['sha256'],
              'files': manifest, 'entries': entries,
              'picker_mode': config.get('Misc', {}).get('Boot', {}).get('PickerMode'),
              'oc_version': 'not-inferred', 'boot_verified': False}
    return report, config


def audit(efi, baseline=None, oc_reference=None):
    current, config = inventory(efi)
    report = {'schema': 'efi-audit-v1', 'created_utc': utc(),
              'scope': 'static-only; enabled is not loaded; no compatibility verdict',
              'current': current}
    if baseline is not None:
        previous, previous_config = inventory(baseline)
        a, b = previous['files'], current['files']
        report['baseline'] = previous
        report['comparison'] = {
            'added_files': sorted(set(b) - set(a)),
            'removed_files': sorted(set(a) - set(b)),
            'changed_files': sorted(p for p in set(a) & set(b) if a[p] != b[p]),
            'files_identical': a == b,
            'config_change_paths': changes(previous_config, config),
            'config_values_omitted': True,
            'baseline_success': 'not-verified-by-this-tool'}
    if oc_reference is not None:
        reference = Path(oc_reference).absolute()
        no_link(reference)
        matched = {}
        for name in CORE:
            candidate = reference / name
            expected = sha(candidate) if candidate.exists() else None
            actual = current['files'].get(name)
            matched[name] = {'reference': expected, 'actual': actual,
                             'matches': expected is not None and actual == expected}
        report['oc_reference'] = {'core_files': matched,
                                  'all_three_match': all(v['matches'] for v in matched.values()),
                                  'meaning': 'matches supplied bytes only; verify release provenance separately'}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--efi', required=True, type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--oc-reference', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        no_link(args.out.parent)
        if args.out.exists():
            raise ValueError('Output already exists; use a new attempt path')
        for root in (args.efi, args.baseline, args.oc_reference):
            if root is not None and args.out.resolve().is_relative_to(root.resolve()):
                raise ValueError('Output must be outside all input EFI directories')
        report = audit(args.efi, args.baseline, args.oc_reference)
        write_new(args.out, report)
        print(json.dumps({'status': 'report-written', 'scope': 'static-only', 'output': str(args.out)}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError, plistlib.InvalidFileException):
        print(json.dumps({'status': 'failed', 'error': 'EFI_AUDIT_INVALID_INPUT',
                          'next': 'Check stable snapshots, plist structure, confined paths and a new output path'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
