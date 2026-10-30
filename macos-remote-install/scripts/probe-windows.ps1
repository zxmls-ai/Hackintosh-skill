$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
$machine = Get-CimInstance -ClassName Win32_ComputerSystemProduct
$result = [ordered]@{
    schema = 'windows-ssh-probe-v1'
    host = $env:COMPUTERNAME
    user = (whoami.exe | Out-String).Trim()
    uuid = [string]$machine.UUID
    os = 'Windows'
    admin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    temp = [IO.Path]::GetFullPath($env:TEMP)
}
Write-Output ('WINDOWS_SSH_PROBE_V1 ' + ($result | ConvertTo-Json -Compress))
