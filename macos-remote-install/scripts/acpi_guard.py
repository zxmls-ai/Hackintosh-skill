"""Check real ACPI/config files before the guided media stage may advance.

This checks bytes and recorded provenance, not whether an Agent's hardware analysis is true.
"""
import plistlib
import struct
import uuid
from xml.parsers.expat import ExpatError

from agentkit import confined, read_json, sha
from ssh_transport import Fault


def check_acpi_evidence(run, machine, manifest_path):
    proofs=[]

    def proof(entry):
        path=confined(run,entry['path'])
        actual=sha(path)
        if actual['size']==0 or actual['sha256']!=entry['sha256']:
            raise ValueError('File changed or empty')
        proofs.append({'path':entry['path'],**actual})
        return path

    def table(path, signatures):
        if path.stat().st_size>16*1024*1024:
            raise ValueError('ACPI table too large')
        data=path.read_bytes()
        if len(data)<36 or data[:4] not in signatures or struct.unpack_from('<I',data,4)[0]!=len(data) or sum(data)%256:
            raise ValueError('Invalid ACPI header, length or checksum')
        return data[:4]

    try:
        manifest_file=confined(run,manifest_path)
        manifest=read_json(manifest_file)
        if manifest['schema']!='acpi-evidence-v1' or not machine or uuid.UUID(manifest['machine_uuid'])!=uuid.UUID(machine['uuid']):
            raise ValueError('Missing or mismatched machine identity')
        method=manifest['method']
        if method not in ('windows-python','windows-native','opencore-sysreport'):
            raise ValueError('Unknown collection method')
        proof(manifest['capture_log'])
        if method=='opencore-sysreport':
            proof(manifest['user_choice'])
        sources=set(); signatures=[]
        for entry in manifest['tables']:
            path=proof(entry)
            if path in sources: raise ValueError('Duplicate table path')
            sources.add(path)
            signatures.append(table(path,(b'DSDT',b'SSDT')))
        if b'DSDT' not in signatures:
            raise ValueError('No DSDT')
        config_path=proof(manifest['config'])
        config=plistlib.loads(config_path.read_bytes())
        debug=config.get('Misc',{}).get('Debug',{})
        target=debug.get('Target')
        if type(target) is not int or target & 0x41 != 0x41 or debug.get('AppleDebug') is not True:
            raise Fault('EFI_DIAGNOSTICS_INVALID')
        proof(manifest['assessment'])
        expected=set()
        for entry in config['ACPI']['Add']:
            if entry.get('Enabled') is not True: continue
            name=entry['Path']
            if not isinstance(name,str) or not name or name.startswith(('/', '\\')) or ':' in name:
                raise ValueError('Invalid ACPI config path')
            expected.add(confined(run,(config_path.parent/'ACPI'/name).relative_to(run).as_posix()))
        declared=set()
        for entry in manifest['patches']:
            path=proof(entry)
            if path in declared: raise ValueError('Duplicate patch')
            declared.add(path)
            table(path,(b'DSDT',b'SSDT'))
            if not isinstance(entry['reason'],str) or not entry['reason'].strip() or not entry['based_on']:
                raise ValueError('Patch needs a source and reason')
            if any(confined(run,p) not in sources for p in entry['based_on']):
                raise ValueError('Unknown source table')
        if declared!=expected:
            raise ValueError('Enabled ACPI files differ from assessment')
        if not expected:
            reason=manifest.get('no_add_reason')
            if not isinstance(reason,str) or not reason.strip():
                raise ValueError('No-Add decision needs an explanation')
        proofs.append({'path':manifest_path,**sha(manifest_file)})
        return proofs
    except Fault:
        raise
    except (KeyError,ValueError,TypeError,OSError,AttributeError,struct.error,plistlib.InvalidFileException,ExpatError):
        raise Fault('ACPI_EVIDENCE_INVALID') from None
