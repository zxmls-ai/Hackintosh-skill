"""Execute the shipped handoff with all OS queries and mutations mocked."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHELL = shutil.which('powershell') or shutil.which('pwsh')
MOCKS = r'''
$script:calls = [System.Collections.Generic.List[string]]::new()
$script:messages = [System.Collections.Generic.List[string]]::new()
$script:packets = [System.Collections.Generic.List[string]]::new()
$script:present = $scenario -notin @('new','install-fails','restart','unknown','installed-no-service','post-not-installed')
$script:running = $false
$script:mode = 'Manual'
$script:probes = 0
$script:rule = $null
$script:ruleParams = $null
if ($scenario -in @('disabled-rule','wrong-port-rule')) {
    $script:rule = [pscustomobject]@{Name='Hackintosh-Skill-SSH-In-TCP';Enabled='False';Profile='Private';Direction='Inbound';Action='Allow'}
    $script:ruleParams = @{Protocol='TCP';LocalPort=2222;RemoteAddress='198.51.100.99'}
}
function Write-Host { param($Object) $script:messages.Add([string]$Object) }
function Write-Warning { param($Message) $script:messages.Add([string]$Message) }
function Get-Service {
    [CmdletBinding()] param($Name)
    $script:calls.Add('get-service')
    if ($script:present) { [pscustomobject]@{Name='sshd';Status=$(if ($script:running) {'Running'} else {'Stopped'})} }
}
function Get-WindowsCapability {
    [CmdletBinding()] param([switch]$Online,$Name)
    $script:calls.Add('get-capability')
    if ($scenario -eq 'unknown') { return }
    $state = if ($scenario -eq 'installed-no-service' -or ($script:present -and $scenario -ne 'post-not-installed')) {'Installed'} else {'NotPresent'}
    [pscustomobject]@{State=$state}
}
function Add-WindowsCapability {
    [CmdletBinding()] param([switch]$Online,$Name)
    $script:calls.Add('install')
    if ($scenario -eq 'install-fails') { throw 'SYNTHETIC_INSTALL_FAILURE' }
    $script:present = $true
    [pscustomobject]@{RestartNeeded=($scenario -eq 'restart')}
}
function Set-Service {
    [CmdletBinding()] param($Name,$StartupType)
    $script:calls.Add('configure')
    if ($StartupType -ne 'Automatic') { throw 'Must set auto startup' }
    if ($scenario -ne 'auto-not-applied') { $script:mode = 'Auto' }
}
function Start-Service {
    [CmdletBinding()] param($Name)
    $script:calls.Add('start')
    if ($scenario -eq 'start-fails') { throw 'SYNTHETIC_START_FAILURE' }
    $script:running = $true
}
function Get-CimInstance {
    [CmdletBinding()] param($ClassName,$Filter)
    if ($ClassName -ne 'Win32_Service' -or $Filter -ne "Name='sshd'") { throw 'Unexpected CIM query' }
    [pscustomobject]@{Name='sshd';State=$(if ($script:running) {'Running'} else {'Stopped'});StartMode=$script:mode;ProcessId=4422}
}
function Get-NetIPAddress {
    [CmdletBinding()] param($AddressFamily)
    if ($scenario -ne 'no-ip') { [pscustomobject]@{IPAddress='198.51.100.20';PrefixLength=$(if ($scenario -eq 'prefix-25') {25} elseif ($scenario -eq 'prefix-23') {23} else {24});AddressState='Preferred';InterfaceAlias='Ethernet'} }
    if ($scenario -eq 'multi-nic') { [pscustomobject]@{IPAddress='203.0.113.20';PrefixLength=24;AddressState='Preferred';InterfaceAlias='Ethernet2'} }
    [pscustomobject]@{IPAddress='127.0.0.1';AddressState='Preferred';InterfaceAlias='Loopback'}
    [pscustomobject]@{IPAddress='169.254.1.2';AddressState='Preferred';InterfaceAlias='Disconnected'}
}
function Get-NetTCPConnection {
    [CmdletBinding()] param($State,$LocalPort)
    $script:probes++
    if ($scenario -eq 'no-listener' -or ($scenario -eq 'delayed-listener' -and $script:probes -lt 3)) { return }
    if ($scenario -eq 'custom-port' -and $LocalPort) { return }
    $address = switch ($scenario) { 'loopback-only' {'127.0.0.1'} 'stale-bind' {'198.51.100.88'} 'specific-bind' {'198.51.100.20'} default {'0.0.0.0'} }
    [pscustomobject]@{LocalPort=$(if ($scenario -eq 'custom-port') {2222} else {22});LocalAddress=$address;OwningProcess=$(if ($scenario -eq 'foreign-listener') {5555} else {4422})}
}
function Start-Sleep { param($Seconds) $script:calls.Add('wait') }
function Get-NetFirewallRule {
    [CmdletBinding()] param($PolicyStore,$Name)
    if ($Name -ne 'Hackintosh-Skill-SSH-In-TCP') { throw 'Unexpected rule access' }
    $script:calls.Add('read-rule-' + $PolicyStore)
    if ($scenario -eq 'policy-hidden' -and $PolicyStore -eq 'ActiveStore') { throw 'SYNTHETIC_POLICY_FAILURE' }
    $script:rule
}
function New-NetFirewallRule {
    [CmdletBinding()] param($Name,$PolicyStore,$Enabled,$Direction,$Action,$Profile,$Protocol,$LocalPort,$RemoteAddress,$Service,$DisplayName)
    $script:calls.Add('new-rule')
    if ($scenario -eq 'firewall-write-fails') { throw 'SYNTHETIC_FIREWALL_FAILURE' }
    $script:ruleParams = @{} + $PSBoundParameters
    $script:rule = [pscustomobject]@{Name=$Name;Enabled=$Enabled;Direction=$Direction;Action=$Action;Profile=$Profile}
}
function Set-NetFirewallRule {
    [CmdletBinding()] param($Name,$PolicyStore,$Enabled,$Direction,$Action,$Profile,$Protocol,$LocalPort,$RemoteAddress,$Service)
    $script:calls.Add('set-rule')
    $script:ruleParams = @{} + $PSBoundParameters
    $script:rule = [pscustomobject]@{Name=$Name;Enabled=$Enabled;Direction=$Direction;Action=$Action;Profile=$Profile}
}
function Get-NetFirewallPortFilter {
    [CmdletBinding()] param($AssociatedNetFirewallRule)
    [pscustomobject]@{Protocol=$script:ruleParams.Protocol;LocalPort=$(if ($scenario -eq 'wrong-effective-port') {445} else {$script:ruleParams.LocalPort})}
}
function Get-NetFirewallAddressFilter {
    [CmdletBinding()] param($AssociatedNetFirewallRule)
    [pscustomobject]@{RemoteAddress=@($script:ruleParams.RemoteAddress)}
}
function Get-NetFirewallProfile {
    [CmdletBinding()] param($PolicyStore)
    [pscustomobject]@{Name='Public';Enabled='True';AllowInboundRules='True';AllowLocalFirewallRules='True'}
}
function whoami.exe { 'example-pc\testuser' }
function Test-Path { [CmdletBinding()] param($LiteralPath) $scenario -ne 'no-keygen' }
function Get-ChildItem {
    [CmdletBinding()] param($LiteralPath,$Filter,[switch]$File)
    if ($Filter -ne 'ssh_host_*_key.pub' -or -not $File) { throw 'Must only read public host keys' }
    if ($scenario -ne 'no-host-keys') {
        [pscustomobject]@{FullName='C:\fixture\ssh_host_ed25519_key.pub'}
        [pscustomobject]@{FullName='C:\fixture\ssh_host_rsa_key.pub'}
    }
}
function Invoke-MockKeygen {
    param([switch]$l,$E,$f)
    if (-not $l -or $E -ne 'sha256' -or $f -notlike '*.pub') { throw 'Unexpected keygen arguments' }
    $global:LASTEXITCODE = 0
    if ($scenario -eq 'keygen-fails') { $global:LASTEXITCODE=1; return 'Failure' }
    if ($scenario -eq 'bad-fingerprint') { return '256 MD5:bad example (ED25519)' }
    $algorithm = if ($f -like '*rsa*') {'RSA'} else {'ED25519'}
    '256 SHA256:' + ('A' * 43) + ' example@fixture (' + $algorithm + ')'
}
function Write-Output { param($InputObject) $script:packets.Add([string]$InputObject) }
'''


def ps_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def documented_code():
    text = (ROOT / 'macos-remote-install/SKILL.md').read_text(encoding='utf-8')
    segment = text.split('<!-- windows-ssh-setup:start -->', 1)[1].split('<!-- windows-ssh-setup:end -->', 1)[0]
    return re.search(r'```powershell\s*\n(.*?)```', segment, re.S).group(1).rstrip()


class HandoffSourceTests(unittest.TestCase):
    def test_documented_code_matches_shipped_script(self):
        source = (ROOT / 'macos-remote-install/scripts/enable-windows-ssh.ps1').read_text(encoding='utf-8-sig').rstrip()
        self.assertEqual(documented_code(), source)


@unittest.skipUnless(os.name == 'nt' and SHELL, 'Windows PowerShell required for mocked handoff')
class SSHHandoffTests(unittest.TestCase):
    def run_scenario(self, scenario, twice=False, b_ips=()):
        code = documented_code()
        # Only substitute the read-only token check; no test requires administrator access.
        code, count = re.subn(r'(?m)^\s*\$isAdmin = .*$', '        $isAdmin = ' + ('$false' if scenario == 'not-admin' else '$true'), code)
        self.assertEqual(count, 1)
        self.assertEqual(code.count('& $keygen '), 1)
        code = code.replace('& $keygen ', 'Invoke-MockKeygen ')
        code, count = re.subn(r'(?m)^    \$BIPv4 = .*$', '    $BIPv4 = @(' + ','.join(ps_string(ip) for ip in b_ips) + ')', code)
        self.assertEqual(count, 1)
        with tempfile.TemporaryDirectory(prefix='ssh-handoff-mock-') as directory:
            fixture = Path(directory) / 'fixture.ps1'
            report = Path(directory) / 'result.json'
            safety_check = r'''
$parseTokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($handoff, [ref]$parseTokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Snippet syntax error' }
$allowed = @('Get-Service','Get-WindowsCapability','Add-WindowsCapability','Set-Service','Start-Service',
'Get-CimInstance','Get-NetIPAddress','Where-Object','Get-NetTCPConnection','Start-Sleep','Select-Object','Format-Table',
'Get-NetFirewallRule','Set-NetFirewallRule','New-NetFirewallRule','Get-NetFirewallPortFilter','Get-NetFirewallAddressFilter',
'Get-NetFirewallProfile','Out-Null','whoami.exe','Write-Host','Write-Warning','Out-String','Join-Path',
'Test-Path','Get-ChildItem','Invoke-MockKeygen','Test-IPv4Subnet','ForEach-Object','Write-Output','ConvertTo-Json')
foreach ($cmd in $ast.FindAll({param($node) $node -is [System.Management.Automation.Language.CommandAst]}, $true)) {
    $name = $cmd.GetCommandName()
    if ($name -and $name -notin $allowed) { throw ('Unmocked command: ' + $name) }
}
$failure = $null
try { for ($i=0; $i -lt $runs; $i++) { & ([scriptblock]::Create($handoff)) } } catch { $failure = $_.Exception.Message }
'''
            script = '$scenario=' + ps_string(scenario) + '\n$runs=' + ('2' if twice else '1') + '\n' + MOCKS
            script += '\n$handoff=' + ps_string(code) + '\n' + safety_check
            script += '\n[pscustomobject]@{calls=@($script:calls.ToArray());running=$script:running;mode=$script:mode;failure=$failure;rule=$script:rule;params=$script:ruleParams;messages=@($script:messages.ToArray());packets=@($script:packets.ToArray())} | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -LiteralPath ' + ps_string(report)
            fixture.write_text(script, encoding='utf-8-sig')
            result = subprocess.run([SHELL, '-NoProfile', '-NonInteractive', '-File', str(fixture)],
                                    capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertTrue(report.exists(), result.stderr.decode(errors='replace'))
            r = json.loads(report.read_text(encoding='utf-8-sig'))
            self.assertIsNone(r['failure'], r['failure'])
            self.assertEqual(len(r['packets']), 2 if twice else 1)
            self.assertTrue(r['packets'][-1].startswith('SSH_HANDOFF_V1 '))
            r['packet'] = json.loads(r['packets'][-1].split(' ', 1)[1])
            self.assertEqual(r['packet']['schema'], 'ssh-handoff-v1')
            self.assertEqual(r['packet']['stage'], '00')
            return r

    def assert_ready(self, r):
        self.assertIsNone(r['failure'])
        self.assertTrue(r['running'])
        self.assertEqual(r['mode'], 'Auto')
        for key, value in dict(Enabled='True',Direction='Inbound',Action='Allow',Profile='Any').items():
            self.assertEqual(r['rule'][key], value)
        for key, value in dict(PolicyStore='PersistentStore',Protocol='TCP',LocalPort=22,RemoteAddress='LocalSubnet',Service='sshd').items():
            self.assertEqual(r['params'][key], value)
        self.assertIn('read-rule-ActiveStore', r['calls'])
        self.assertEqual(r['packet']['status'], 'local-ready', r['packet'])
        self.assertEqual(r['packet']['user'], 'example-pc\\testuser')
        self.assertEqual(r['packet']['port'], 22)
        self.assertEqual(len(r['packet']['host_keys']), 2)
        self.assertEqual(r['packet']['network']['connectivity'], 'pending-b-test')

    def assert_not_ready(self, r):
        self.assertEqual(r['packet']['status'], 'failed')
        self.assertTrue(r['packet']['error'])
        self.assertTrue(r['packet']['failed_step'])

    def test_missing_service_installs_configures_and_listens(self):
        r = self.run_scenario('new')
        self.assert_ready(r)
        self.assertEqual(r['calls'].count('install'), 1)
        self.assertLess(r['calls'].index('install'), r['calls'].index('configure'))
        self.assertEqual(r['calls'].count('get-capability'), 2)

    def test_existing_service_does_not_reinstall(self):
        r = self.run_scenario('existing')
        self.assert_ready(r)
        self.assertNotIn('get-capability', r['calls'])
        self.assertNotIn('install', r['calls'])

    def test_install_error_stops_before_configuring(self):
        r = self.run_scenario('install-fails')
        self.assert_not_ready(r)
        self.assertNotIn('configure', r['calls'])

    def test_restart_required_does_not_claim_configuration_done(self):
        r = self.run_scenario('restart')
        self.assertIsNone(r['failure'])
        self.assertFalse(r['running'])
        self.assertNotIn('configure', r['calls'])
        self.assertEqual(r['packet']['status'], 'restart-required')

    def test_unknown_component_refuses_install(self):
        r = self.run_scenario('unknown')
        self.assert_not_ready(r)
        self.assertNotIn('install', r['calls'])

    def test_installed_but_missing_service_stops(self):
        r = self.run_scenario('installed-no-service')
        self.assert_not_ready(r)
        self.assertNotIn('start', r['calls'])

    def test_incomplete_install_stops(self):
        r = self.run_scenario('post-not-installed')
        self.assert_not_ready(r)
        self.assertNotIn('configure', r['calls'])

    def test_start_failure_stops(self):
        r = self.run_scenario('start-fails')
        self.assert_not_ready(r)
        self.assertFalse(r['running'])

    def test_not_admin_does_not_mutate(self):
        r = self.run_scenario('not-admin')
        self.assert_not_ready(r)
        self.assertEqual(r['calls'], [])

    def test_delayed_listener_is_waited_for(self):
        r = self.run_scenario('delayed-listener')
        self.assert_ready(r)
        self.assertEqual(r['calls'].count('wait'), 2)

    def test_specific_current_ip_binding_is_accepted(self):
        self.assert_ready(self.run_scenario('specific-bind'))

    def test_missing_listener_does_not_open_firewall(self):
        r = self.run_scenario('no-listener')
        self.assert_not_ready(r)
        self.assertNotIn('new-rule', r['calls'])
        self.assertEqual(r['calls'].count('wait'), 15)

    def test_other_process_on_22_is_not_ssh_success(self):
        self.assert_not_ready(self.run_scenario('foreign-listener'))

    def test_loopback_listener_is_not_remote_ready(self):
        self.assert_not_ready(self.run_scenario('loopback-only'))

    def test_old_ip_binding_is_not_remote_ready(self):
        self.assert_not_ready(self.run_scenario('stale-bind'))

    def test_custom_port_is_not_silently_overwritten(self):
        r = self.run_scenario('custom-port')
        self.assert_not_ready(r)
        self.assertNotIn('new-rule', r['calls'])

    def test_no_valid_ipv4_is_not_ready(self):
        self.assert_not_ready(self.run_scenario('no-ip'))

    def test_startup_mode_is_read_back(self):
        self.assert_not_ready(self.run_scenario('auto-not-applied'))

    def test_disabled_rule_is_repaired(self):
        r = self.run_scenario('disabled-rule')
        self.assert_ready(r)
        self.assertIn('set-rule', r['calls'])
        self.assertNotIn('new-rule', r['calls'])

    def test_wrong_port_and_narrow_profile_are_repaired(self):
        self.assert_ready(self.run_scenario('wrong-port-rule'))

    def test_rerun_does_not_duplicate_install_or_rule(self):
        r = self.run_scenario('new', twice=True)
        self.assert_ready(r)
        self.assertEqual(r['calls'].count('install'), 1)
        self.assertEqual(r['calls'].count('new-rule'), 1)
        self.assertEqual(r['calls'].count('set-rule'), 1)

    def test_firewall_write_error_is_not_success(self):
        self.assert_not_ready(self.run_scenario('firewall-write-fails'))

    def test_missing_effective_rule_is_not_success(self):
        self.assert_not_ready(self.run_scenario('policy-hidden'))

    def test_wrong_effective_port_is_not_success(self):
        self.assert_not_ready(self.run_scenario('wrong-effective-port'))

    def test_handoff_has_addresses_prefixes_and_public_fingerprints(self):
        r = self.run_scenario('existing', b_ips=['198.51.100.10'])
        self.assert_ready(r)
        p = r['packet']
        self.assertEqual(p['ipv4'][0]['ip'], '198.51.100.20')
        self.assertEqual(p['ipv4'][0]['prefix'], 24)
        self.assertEqual({k['algorithm'] for k in p['host_keys']}, {'ED25519', 'RSA'})
        self.assertNotIn('password', p)
        self.assertNotIn('private_key', p)
        self.assertEqual(len(r['messages']), 4)  # One waiting notice, then three handoff lines.

    def test_known_same_subnet_still_needs_b_connectivity_test(self):
        r = self.run_scenario('existing', b_ips=['198.51.100.10'])
        self.assert_ready(r)
        self.assertTrue(r['packet']['network']['same_subnet_from_a'])
        self.assertEqual(r['packet']['network']['connectivity'], 'pending-b-test')

    def test_unknown_b_is_not_assumed_on_same_lan(self):
        r = self.run_scenario('existing')
        self.assert_ready(r)
        self.assertIsNone(r['packet']['network']['same_subnet_from_a'])

    def test_matching_first_three_octets_not_sufficient_for_25(self):
        r = self.run_scenario('prefix-25', b_ips=['198.51.100.200'])
        self.assert_ready(r)
        self.assertFalse(r['packet']['network']['same_subnet_from_a'])

    def test_different_third_octet_can_match_23(self):
        r = self.run_scenario('prefix-23', b_ips=['198.51.101.10'])
        self.assert_ready(r)
        self.assertTrue(r['packet']['network']['same_subnet_from_a'])

    def test_multiple_nics_preserved_and_match_selected(self):
        r = self.run_scenario('multi-nic', b_ips=['203.0.113.10'])
        self.assert_ready(r)
        self.assertEqual(len(r['packet']['ipv4']), 2)
        self.assertEqual(r['packet']['network']['matching_a'], ['203.0.113.20'])

    def test_other_subnet_not_reported_as_connected_or_setup_failure(self):
        r = self.run_scenario('existing', b_ips=['203.0.113.10'])
        self.assert_ready(r)
        self.assertFalse(r['packet']['network']['same_subnet_from_a'])

    def test_keygen_error_is_not_trusted_fingerprint(self):
        self.assert_not_ready(self.run_scenario('keygen-fails'))

    def test_missing_keygen_returns_one_error_packet(self):
        self.assert_not_ready(self.run_scenario('no-keygen'))

    def test_missing_host_keys_are_not_silently_ignored(self):
        self.assert_not_ready(self.run_scenario('no-host-keys'))

    def test_invalid_fingerprint_is_rejected(self):
        self.assert_not_ready(self.run_scenario('bad-fingerprint'))


if __name__ == '__main__':
    unittest.main()
