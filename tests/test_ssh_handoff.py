"""Execute the actual documented fallback with all service/component calls mocked."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHELL = shutil.which("powershell") or shutil.which("pwsh")
MOCKS = r'''
$script:calls = [System.Collections.Generic.List[string]]::new()
$script:present = $scenario -eq 'existing'
$script:running = $false
function Get-Service {
    [CmdletBinding()] param($Name)
    $script:calls.Add('get-service')
    if ($script:present) {
        [pscustomobject]@{Name='sshd';Status=$(if ($script:running) {'Running'} else {'Stopped'})}
    }
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
    if ($scenario -eq 'install-fails') { Write-Error 'SYNTHETIC_INSTALL_FAILURE'; return }
    $script:present = $true
    [pscustomobject]@{RestartNeeded=($scenario -eq 'restart')}
}
function Set-Service {
    [CmdletBinding()] param($Name,$StartupType)
    $script:calls.Add('configure')
}
function Start-Service {
    [CmdletBinding()] param($Name)
    $script:calls.Add('start')
    if ($scenario -eq 'start-fails') { Write-Error 'SYNTHETIC_START_FAILURE'; return }
    $script:running = $true
}
'''


def ps_string(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(os.name == "nt" and SHELL, "Windows PowerShell required for mocked handoff")
class SSHHandoffTests(unittest.TestCase):
    def run_scenario(self, scenario):
        text = (ROOT / "macos-remote-install/SKILL.md").read_text(encoding="utf-8")
        segment = text.split("<!-- windows-ssh-fallback:start -->", 1)[1].split("<!-- windows-ssh-fallback:end -->", 1)[0]
        code = re.search(r"```powershell\s*\n(.*?)```", segment, re.S).group(1)
        with tempfile.TemporaryDirectory(prefix="ssh-handoff-mock-") as directory:
            fixture = Path(directory) / "fixture.ps1"
            report = Path(directory) / "result.json"
            # Refuse to run if a future edit introduces an unmocked external command.
            safety_check = r'''
$parseTokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($handoff, [ref]$parseTokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Snippet syntax error' }
$allowed = @('Get-Service','Get-WindowsCapability','Add-WindowsCapability','Set-Service','Start-Service','Write-Host','Write-Warning')
foreach ($cmd in $ast.FindAll({param($node) $node -is [System.Management.Automation.Language.CommandAst]}, $true)) {
    $name = $cmd.GetCommandName()
    if ($name -and $name -notin $allowed) { throw ('Unmocked command: ' + $name) }
}
$failure = $null
try { & ([scriptblock]::Create($handoff)) } catch { $failure = $_.Exception.Message }
'''
            script = "$scenario=" + ps_string(scenario) + "\n" + MOCKS
            script += "\n$handoff=" + ps_string(code) + "\n" + safety_check
            script += "\n[pscustomobject]@{calls=@($script:calls.ToArray());running=$script:running;failure=$failure} | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -LiteralPath " + ps_string(report)
            fixture.write_text(script, encoding="utf-8-sig")
            result = subprocess.run([SHELL, "-NoProfile", "-NonInteractive", "-File", str(fixture)],
                                    capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertTrue(report.exists(), result.stderr.decode(errors="replace"))
            return json.loads(report.read_text(encoding="utf-8-sig"))

    def test_missing_service_installs_then_starts(self):
        r = self.run_scenario("new")
        self.assertIsNone(r["failure"])
        self.assertTrue(r["running"])
        self.assertEqual(r["calls"].count("install"), 1)
        self.assertLess(r["calls"].index("install"), r["calls"].index("configure"))
        self.assertEqual(r["calls"].count("get-capability"), 2)

    def test_existing_service_does_not_reinstall(self):
        r = self.run_scenario("existing")
        self.assertTrue(r["running"])
        self.assertNotIn("get-capability", r["calls"])
        self.assertNotIn("install", r["calls"])

    def test_install_error_stops_before_configuring(self):
        r = self.run_scenario("install-fails")
        self.assertIn("SYNTHETIC_INSTALL_FAILURE", r["failure"])
        self.assertNotIn("configure", r["calls"])
        self.assertNotIn("start", r["calls"])

    def test_restart_required_returns_before_start(self):
        r = self.run_scenario("restart")
        self.assertIsNone(r["failure"])
        self.assertFalse(r["running"])
        self.assertNotIn("configure", r["calls"])
        self.assertNotIn("start", r["calls"])

    def test_unknown_component_refuses_to_install(self):
        r = self.run_scenario("unknown")
        self.assertIsNotNone(r["failure"])
        self.assertNotIn("install", r["calls"])
        self.assertNotIn("start", r["calls"])

    def test_installed_but_missing_service_stops(self):
        r = self.run_scenario("installed-no-service")
        self.assertIsNotNone(r["failure"])
        self.assertNotIn("install", r["calls"])
        self.assertNotIn("start", r["calls"])

    def test_incomplete_install_does_not_start(self):
        r = self.run_scenario("post-not-installed")
        self.assertIsNotNone(r["failure"])
        self.assertIn("install", r["calls"])
        self.assertNotIn("configure", r["calls"])
        self.assertNotIn("start", r["calls"])

    def test_start_failure_does_not_claim_running(self):
        r = self.run_scenario("start-fails")
        self.assertIn("SYNTHETIC_START_FAILURE", r["failure"])
        self.assertFalse(r["running"])


if __name__ == "__main__":
    unittest.main()
