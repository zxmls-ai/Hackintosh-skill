"""Prepare the reviewed SSH script on B; only fill verified B IPv4 addresses."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re

from agentkit import no_link

SOURCE = Path(__file__).with_name('enable-windows-ssh.ps1')
IP_LINE = re.compile(r'^    \$BIPv4 = @\(\).*$', re.MULTILINE)


def render(source, addresses):
    validated = list(dict.fromkeys(str(ipaddress.IPv4Address(a)) for a in addresses))
    lines = IP_LINE.findall(source)
    if len(lines) != 1:
        raise ValueError('Expected exactly one untouched BIPv4 placeholder')
    replacement = "    $BIPv4 = @(" + ', '.join("'" + a + "'" for a in validated) + ')'
    prepared, count = IP_LINE.subn(lambda _: replacement, source)
    if count != 1 or prepared.replace(replacement, lines[0], 1) != source:
        raise ValueError('Unexpected changes outside the BIPv4 parameter')
    return prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--b-ip', action='append', default=[], help='Verified IPv4 of B; repeat for multiple interfaces')
    parser.add_argument('--out', required=True, type=Path, help='New .ps1 path in an existing private staging directory on B')
    args = parser.parse_args()
    no_link(SOURCE)
    prepared = render(SOURCE.read_text(encoding='utf-8-sig'), args.b_ip)
    no_link(args.out.parent)
    data = prepared.encode('utf-8-sig')
    with args.out.open('xb') as handle:
        handle.write(data)
    print(json.dumps({'file':str(args.out.resolve()), 'sha256':hashlib.sha256(data).hexdigest(),
                      'changes':'BIPv4 only', 'executed':False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
