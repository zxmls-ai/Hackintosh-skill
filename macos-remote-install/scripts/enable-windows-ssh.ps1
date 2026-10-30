& {
    $ErrorActionPreference = 'Stop'
    $BIPv4 = @() # Agent 在发给用户前填入 B 的实际 IPv4；获取不到时保持空。
    $step = '权限检查'
    $report = [ordered]@{schema='ssh-handoff-v1';status='failed';stage='00'}
    function Test-IPv4Subnet([string]$A, [string]$B, [int]$Prefix) {
        if ($Prefix -lt 0 -or $Prefix -gt 32) { throw 'IPv4 前缀长度无效。' }
        $aa = [Net.IPAddress]::Parse($A).GetAddressBytes()
        $bb = [Net.IPAddress]::Parse($B).GetAddressBytes()
        if ($aa.Length -ne 4 -or $bb.Length -ne 4) { throw '网段比较需要 IPv4 地址。' }
        for ($bit = 0; $bit -lt $Prefix; $bit++) {
            $index = [int][Math]::Floor($bit / 8)
            $mask = 1 -shl (7 - ($bit % 8))
            if (($aa[$index] -band $mask) -ne ($bb[$index] -band $mask)) { return $false }
        }
        return $true
    }
    Write-Host '进度：00 远程接入｜正在安装、校验并生成连接信息，请等待。'
    try {
        $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if (-not $isAdmin) { throw '请在 A 电脑以管理员身份打开 Windows PowerShell，再粘贴整块代码。' }

        $step = '安装服务器'
        if (-not (Get-Service -Name sshd -ErrorAction SilentlyContinue)) {
            $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
            if ($cap.State -eq 'NotPresent') {
                $setup = Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
                if ($setup.RestartNeeded) {
                    $report.status = 'restart-required'
                    throw '组件要求重启；重启后再运行这整块代码。'
                }
                $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
            }
            if ($cap.State -ne 'Installed') { throw '组件状态不是 Installed，请把完整输出发给 Agent。' }
        }
        if (-not (Get-Service -Name sshd -ErrorAction SilentlyContinue)) {
            throw '组件已安装但没有 sshd 服务，请把完整输出发给 Agent。'
        }

        $step = '启动并检查监听'
        Set-Service -Name sshd -StartupType Automatic
        Start-Service -Name sshd
        $listen = @()
        for ($attempt = 0; $attempt -lt 15; $attempt++) {
            $svc = Get-CimInstance -ClassName Win32_Service -Filter "Name='sshd'"
            $lan = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
                $_.AddressState -eq 'Preferred' -and $_.IPAddress -notmatch '^(127\.|169\.254\.)'
            })
            $listen = @(Get-NetTCPConnection -State Listen -LocalPort 22 -ErrorAction SilentlyContinue | Where-Object {
                $_.OwningProcess -eq $svc.ProcessId -and
                ($_.LocalAddress -in @('0.0.0.0', '::') -or $_.LocalAddress -in $lan.IPAddress)
            })
            if ($svc.State -eq 'Running' -and $svc.StartMode -eq 'Auto' -and $listen.Count -gt 0) { break }
            Start-Sleep -Seconds 1
        }
        if ($svc.State -ne 'Running' -or $svc.StartMode -ne 'Auto' -or $listen.Count -eq 0) {
            throw 'sshd 尚未以自动服务监听可远程访问的 TCP 22。请把输出发给 Agent，检查服务日志、Port/ListenAddress 和端口占用；不自动覆盖已有配置。'
        }

        if ($lan.Count -eq 0) { throw '没有可用的网卡 IPv4，请先检查网线、Wi-Fi 或 DHCP，再重新执行。' }
        $step = '配置防火墙'
        $ruleName = 'Hackintosh-Skill-SSH-In-TCP'
        $ruleOptions = @{
            Name=$ruleName; PolicyStore='PersistentStore'; Enabled='True'
            Direction='Inbound'; Action='Allow'; Profile='Any'; Protocol='TCP'
            LocalPort=22; RemoteAddress='LocalSubnet'; Service='sshd'
        }
        if (Get-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName -ErrorAction SilentlyContinue) {
            Set-NetFirewallRule @ruleOptions
        } else {
            New-NetFirewallRule @ruleOptions -DisplayName 'Hackintosh Skill - Windows SSH (LAN)' | Out-Null
        }
        $rule = Get-NetFirewallRule -PolicyStore ActiveStore -Name $ruleName
        $port = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
        $address = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule
        if ($rule.Enabled -ne 'True' -or $rule.Direction -ne 'Inbound' -or $rule.Action -ne 'Allow' -or
            $rule.Profile -ne 'Any' -or $port.Protocol -notin @('TCP','6') -or
            $port.LocalPort -ne '22' -or $address.RemoteAddress -notcontains 'LocalSubnet') {
            throw '防火墙规则核验未通过，请把输出发给 Agent；不要关闭整个防火墙。'
        }


        $step = '生成连接信息'
        $username = (whoami.exe | Out-String).Trim()
        if (-not $username) { throw '未能取得当前账户名。' }
        $keygen = Join-Path $env:WINDIR 'System32\OpenSSH\ssh-keygen.exe'
        if (-not (Test-Path -LiteralPath $keygen)) { throw '未找到系统 ssh-keygen；需要 Agent 核对当前 OpenSSH 安装来源。' }
        $keyDirectory = Join-Path $env:ProgramData 'ssh'
        $fingerprints = @()
        foreach ($keyFile in @(Get-ChildItem -LiteralPath $keyDirectory -Filter 'ssh_host_*_key.pub' -File)) {
            $keyText = (& $keygen -l -E sha256 -f $keyFile.FullName | Out-String).Trim()
            if ($LASTEXITCODE -ne 0 -or $keyText -notmatch '(SHA256:[A-Za-z0-9+/]+)\s+.*\(([^)]+)\)$') {
                throw '主机公钥指纹读取失败。'
            }
            $fingerprints += [ordered]@{algorithm=$Matches[2];sha256=$Matches[1]}
        }
        if ($fingerprints.Count -eq 0) { throw '默认目录没有主机公钥；需要 Agent 检查服务配置与 HostKey 路径。' }
        $matching = @()
        foreach ($a in $lan) {
            foreach ($b in $BIPv4) {
                if (Test-IPv4Subnet $a.IPAddress $b $a.PrefixLength) { $matching += $a.IPAddress; break }
            }
        }
        $sameSubnet = if ($BIPv4.Count -eq 0) { $null } else { $matching.Count -gt 0 }
        $report.status = 'local-ready'
        $report.host = $env:COMPUTERNAME
        $report.user = $username
        $report.port = 22
        $report.ipv4 = @($lan | ForEach-Object { [ordered]@{ip=$_.IPAddress;prefix=$_.PrefixLength;interface=$_.InterfaceAlias} })
        $report.host_keys = $fingerprints
        $report.checks = [ordered]@{service='Running';startup='Auto';listener='sshd:22';firewall='LocalSubnet/AnyProfile'}
        $report.network = [ordered]@{b_ipv4=@($BIPv4);same_subnet_from_a=$sameSubnet;matching_a=@($matching);connectivity='pending-b-test'}
    } catch {
        $report.failed_step = $step
        $report.error = $_.Exception.Message
    }
    if ($report.status -eq 'local-ready') {
        Write-Host '进度：00 远程接入｜本机配置与检查完成。'
        Write-Host '下一步：B 自动核对指纹、连接 SSH 并采集硬件。'
        Write-Host '需要你：将下面整行结果发给 B；如尚未提供，再补充账户密码和目标 macOS 版本（未定也可以）。'
    } else {
        Write-Host ('进度：00 远程接入｜未完成：' + $step)
        Write-Host '下一步：Agent 根据结果处理错误或安排重启。'
        Write-Host '需要你：将下面整行结果发给 B。'
    }
    Write-Output ('SSH_HANDOFF_V1 ' + ($report | ConvertTo-Json -Depth 6 -Compress))
}
