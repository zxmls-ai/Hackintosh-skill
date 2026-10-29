"""Windows collector integration with ALL hardware queries replaced by fixtures."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "macos-remote-install" / "scripts"))
import agentkit
import target_guard

MOCKS = r'''
function Get-CimInstance {
    param([string]$ClassName)
    switch ($ClassName) {
        'Win32_ComputerSystemProduct' { [pscustomobject]@{UUID='synthetic-host';Vendor='Synthetic';Name='Synthetic'} }
        'Win32_OperatingSystem' { [pscustomobject]@{Caption='Synthetic Windows';BuildNumber='1';OSArchitecture='64-bit'} }
        'Win32_BIOS' { [pscustomobject]@{SMBIOSBIOSVersion='Synthetic'} }
        'Win32_BaseBoard' { [pscustomobject]@{Manufacturer='Synthetic';Product='Synthetic'} }
        default { @() }
    }
}
function Get-Disk {
    [pscustomobject]@{Number=3;NumberOfPartitions=$fixturePartitions;UniqueId='synthetic-usb-id';SerialNumber='synthetic-serial';FriendlyName='Synthetic USB';Size=16000000000;BusType='USB';PartitionStyle='GPT';IsBoot=$fixtureRole;IsSystem=$fixtureRole;IsOffline=$false;IsReadOnly=$false;HealthStatus='Healthy'}
}
function Get-Partition {
    param($DiskNumber)
    if ($fixturePartitions -eq 0) { throw 'Empty disk must not query Get-Partition' }
    [pscustomobject]@{PartitionNumber=1;Guid='synthetic-partition';Offset=1048576;Size=8000000000;DriveLetter='U';GptType='ebd0a0a2-b9e5-4433-87c0-68b6b72699c7';Type='Basic';IsBoot=$fixtureRole;IsSystem=$fixtureRole}
}
function Get-Volume { process { [pscustomobject]@{FileSystem='NTFS';FileSystemLabel='SYNTHETIC';SizeRemaining=7000000000} } }
function Get-PartitionSupportedSize { param($DiskNumber,$PartitionNumber) [pscustomobject]@{SizeMin=1000000000;SizeMax=8000000000} }
function Get-NetAdapter { @() }
function Get-NetIPAddress { param($AddressFamily) @() }
function Get-BitLockerVolume { @() }
function Confirm-SecureBootUEFI { $false }
'''


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(os.name == "nt" and (shutil.which("powershell") or shutil.which("pwsh")), "Windows PowerShell required for mocked collector")
class CollectorTests(unittest.TestCase):
    def collect(self, role, count=1):
        with tempfile.TemporaryDirectory(prefix="collector-mock-") as directory:
            root = Path(directory)
            script = root / "fixture.ps1"
            report = root / "report.json"
            text = "$ErrorActionPreference='Stop'\n$fixtureRole=" + role + "\n$fixturePartitions=" + str(count) + "\n" + MOCKS
            text += "\n& " + ps_quote(ROOT / "macos-remote-install/scripts/collect-windows.ps1") + " -OutputPath " + ps_quote(report)
            text += "\nif ($LASTEXITCODE) { exit $LASTEXITCODE }\n"
            script.write_text(text, encoding="utf-8-sig")
            result = subprocess.run([shutil.which("powershell") or shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-File", str(script)],
                                    capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertTrue(report.exists(), result.stderr.decode(errors="replace"))
            return result.returncode, agentkit.read_json(report)

    def test_null_roles_remain_unknown_and_guard_refuses(self):
        code, data = self.collect("$null")
        self.assertEqual(code, 2)
        self.assertEqual(len(data["errors"]), 4)
        disk = data["disks"][0]; part = disk["partitions"][0]
        for record in (disk, part):
            self.assertIsNone(record["is_boot"])
            self.assertIsNone(record["is_system"])
        with self.assertRaises(ValueError): target_guard.make_plan(data, 3, "usb")

    def test_known_non_system_usb_retains_false(self):
        code, data = self.collect("$false")
        self.assertEqual(code, 0)
        self.assertFalse(data["disks"][0]["is_boot"])
        self.assertEqual(data["errors"], [])
        self.assertEqual(target_guard.make_plan(data, 3, "usb")["purpose"], "usb")

    def test_empty_usb_is_an_explicit_empty_layout(self):
        code, data = self.collect("$false", count=0)
        self.assertEqual(code, 0)
        self.assertEqual(data["disks"][0]["partitions"], [])
        self.assertEqual(target_guard.make_plan(data, 3, "usb")["layout"], [])


if __name__ == "__main__": unittest.main()
