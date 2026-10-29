param([Parameter(Mandatory=$true)][string]$OutputPath)
# Read-only inventory. Writes only a NEW report; never changes storage or services.
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Run on target A under Windows.' }
if (-not [System.IO.Path]::IsPathRooted($OutputPath)) { throw 'OutputPath must be absolute.' }
$taskReportPath = [System.IO.Path]::GetFullPath($OutputPath)
if (Test-Path -LiteralPath $taskReportPath) { throw 'Refusing to overwrite an existing report.' }
if (-not (Test-Path -LiteralPath (Split-Path -Parent $taskReportPath) -PathType Container)) { throw 'Output parent must exist.' }
$script:collectionErrors = New-Object 'System.Collections.Generic.List[object]'
function Probe([string]$Section, [scriptblock]$Code) {
    try { & $Code } catch {
        $script:collectionErrors.Add([pscustomobject]@{section=$Section; message=$_.Exception.Message})
    }
}
function Known-Flag($Object, [string]$Property, [string]$Section) {
    if ($null -eq $Object -or $null -eq $Object.PSObject.Properties[$Property] -or $null -eq $Object.$Property) {
        $script:collectionErrors.Add([pscustomobject]@{section=$Section; message=('Missing role flag: ' + $Property)})
        return $null
    }
    return [bool]$Object.$Property
}
$taskHost = @(Probe 'host' { Get-CimInstance Win32_ComputerSystemProduct }) | Select-Object -First 1
$taskOS = @(Probe 'os' { Get-CimInstance Win32_OperatingSystem }) | Select-Object -First 1
$taskBIOS = @(Probe 'bios' { Get-CimInstance Win32_BIOS }) | Select-Object -First 1
$taskBoard = @(Probe 'board' { Get-CimInstance Win32_BaseBoard }) | Select-Object -First 1
$taskDisks = @(foreach ($d in @(Probe 'disk-list' { Get-Disk })) {
    $diskParts = @()
    if ($null -eq $d.NumberOfPartitions -or $d.NumberOfPartitions -ne 0) {
        $diskParts = @(Probe ('partition-list-' + $d.Number) { Get-Partition -DiskNumber $d.Number })
    }
    $parts = @(foreach ($p in $diskParts) {
        $v = @(Probe ('volume-' + $d.Number + '-' + $p.PartitionNumber) { $p | Get-Volume -ErrorAction Stop }) | Select-Object -First 1
        $supported = $null
        if ($v -and $v.FileSystem -eq 'NTFS') {
            $supported = @(Probe ('supported-size-' + $d.Number + '-' + $p.PartitionNumber) {
                Get-PartitionSupportedSize -DiskNumber $d.Number -PartitionNumber $p.PartitionNumber
            }) | Select-Object -First 1
        }
        [pscustomobject]@{
            number=[int]$p.PartitionNumber; guid=[string]$p.Guid; offset_bytes=[long]$p.Offset; size_bytes=[long]$p.Size
            drive_letter=[string]$p.DriveLetter; gpt_type=[string]$p.GptType; type=[string]$p.Type
            is_boot=(Known-Flag $p 'IsBoot' ('partition-role-' + $d.Number)); is_system=(Known-Flag $p 'IsSystem' ('partition-role-' + $d.Number))
            file_system= $(if ($v) {[string]$v.FileSystem} else {$null})
            label= $(if ($v) {[string]$v.FileSystemLabel} else {$null})
            free_bytes= $(if ($v) {[long]$v.SizeRemaining} else {$null})
            supported_min_bytes= $(if ($supported) {[long]$supported.SizeMin} else {$null})
            supported_max_bytes= $(if ($supported) {[long]$supported.SizeMax} else {$null})
        }
    })
    [pscustomobject]@{
        number=[int]$d.Number; unique_id=[string]$d.UniqueId; serial=[string]$d.SerialNumber; model=[string]$d.FriendlyName
        size_bytes=[long]$d.Size; bus_type=[string]$d.BusType; partition_style=[string]$d.PartitionStyle
        is_boot=(Known-Flag $d 'IsBoot' ('disk-role-' + $d.Number)); is_system=(Known-Flag $d 'IsSystem' ('disk-role-' + $d.Number))
        is_offline=$d.IsOffline; is_readonly=$d.IsReadOnly
        health_status=[string]$d.HealthStatus; partitions=$parts
    }
})
$taskCPU = @(Probe 'cpu' { Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,Architecture,NumberOfCores,NumberOfLogicalProcessors })
$taskGPU = @(Probe 'gpu' { Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID,DriverVersion,VideoProcessor })
$taskPnp = @(Probe 'pnp' {
    Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -in @('Display','Net','System','USB','MEDIA','Bluetooth','SCSIAdapter','HIDClass') } |
        Select-Object Name,PNPClass,PNPDeviceID,HardwareID,Status,ConfigManagerErrorCode
})
$taskNetwork = @(Probe 'network' { Get-NetAdapter | Select-Object Name,InterfaceDescription,MacAddress,Status,LinkSpeed,InterfaceGuid,ifIndex })
$taskAddresses = @(Probe 'addresses' { Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceIndex,IPAddress,PrefixLength,AddressState })
$taskBitLocker = @(Probe 'bitlocker-status' { Get-BitLockerVolume | Select-Object MountPoint,VolumeStatus,ProtectionStatus,EncryptionPercentage,LockStatus })
$taskSecureBoot = @(Probe 'secure-boot-status' { Confirm-SecureBootUEFI }) | Select-Object -First 1
$taskAdministrator = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$report = [ordered]@{
    schema_version=1; platform='windows'; captured_at_utc=[DateTime]::UtcNow.ToString('o')
    role_note='Verify this is A. Collection alone does not establish the target role.'
    host=@{uuid=[string]$taskHost.UUID; manufacturer=[string]$taskHost.Vendor; model=[string]$taskHost.Name
        os=[string]$taskOS.Caption; build=[string]$taskOS.BuildNumber; architecture=[string]$taskOS.OSArchitecture
        bios_version=[string]$taskBIOS.SMBIOSBIOSVersion; board_manufacturer=[string]$taskBoard.Manufacturer; board_product=[string]$taskBoard.Product}
    elevated=$taskAdministrator; secure_boot=$taskSecureBoot; cpus=$taskCPU; gpus=$taskGPU; pnp=$taskPnp
    network=$taskNetwork; ipv4=$taskAddresses; disks=$taskDisks; bitlocker=$taskBitLocker; errors=@($script:collectionErrors.ToArray())
}
$json = $report | ConvertTo-Json -Depth 12
$utf8 = New-Object System.Text.UTF8Encoding($false)
$bytes = $utf8.GetBytes($json + [Environment]::NewLine)
$stream = [System.IO.File]::Open($taskReportPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
Write-Output ('Report: ' + $taskReportPath)
Write-Output ('Collection errors: ' + $script:collectionErrors.Count + ' (inspect report.errors before use)')
if ($script:collectionErrors.Count -gt 0) { exit 2 }
