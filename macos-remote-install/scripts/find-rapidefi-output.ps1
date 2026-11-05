param(
    [string[]]$DesktopPath = @(),
    [DateTimeOffset]$StartedAfter = [DateTimeOffset]::MinValue
)
# Run on the Windows host and account where RapidEFI actually generated the files.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$roots = @($DesktopPath)
if ($roots.Count -eq 0) {
    $roots = @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:USERPROFILE 'Desktop'))
}
$roots = @($roots | Where-Object {$_ -and (Test-Path -LiteralPath $_ -PathType Container)} | ForEach-Object {(Get-Item -LiteralPath $_).FullName} | Select-Object -Unique)
$found = @()
foreach ($root in $roots) {
    foreach ($config in @(Get-ChildItem -LiteralPath $root -Filter 'config.plist' -File -Recurse -Depth 6 -ErrorAction SilentlyContinue)) {
        if ($config.Directory.Name -ine 'OC' -or $config.Directory.Parent.Name -ine 'EFI') {continue}
        $efi = $config.Directory.Parent
        if (-not (Test-Path -LiteralPath (Join-Path $efi.FullName 'BOOT\BOOTx64.efi') -PathType Leaf)) {continue}
        $model = @(Get-ChildItem -LiteralPath $efi.Parent.FullName,$efi.FullName -File -Force -ErrorAction SilentlyContinue | Where-Object {$_.Name -like 'configModel*'} | Select-Object -ExpandProperty FullName -Unique)
        $new = $config.LastWriteTimeUtc -ge $StartedAfter.UtcDateTime -or $config.CreationTimeUtc -ge $StartedAfter.UtcDateTime -or $efi.CreationTimeUtc -ge $StartedAfter.UtcDateTime
        if (-not @($found | Where-Object {$_.EFI -ieq $efi.FullName}).Count) {
            $stream = [IO.File]::OpenRead($config.FullName)
            $hasher = [Security.Cryptography.SHA256]::Create()
            try {$digest = ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant()}
            finally {$stream.Dispose();$hasher.Dispose()}
            $found += [ordered]@{EFI=$efi.FullName;Config=$config.FullName;ConfigSHA256=$digest;ModifiedUtc=$config.LastWriteTimeUtc.ToString('o');NewSinceStart=$new;ConfigModel=$model}
        }
    }
}
[ordered]@{Schema='rapidefi-output-v1';DesktopRoots=$roots;Candidates=@($found);Note='Match the generation success path and this run time before selecting a candidate. Existing files alone do not prove generation succeeded.'} | ConvertTo-Json -Depth 5
