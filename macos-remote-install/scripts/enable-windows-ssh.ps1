& {
    $ErrorActionPreference = 'Stop'
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) { throw '请在 A 电脑以管理员身份打开 Windows PowerShell，再粘贴整块代码。' }

    Write-Host '[1/4] 检查并安装 OpenSSH 服务器……'
    if (-not (Get-Service -Name sshd -ErrorAction SilentlyContinue)) {
        $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
        if ($cap.State -eq 'NotPresent') {
            $setup = Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
            if ($setup.RestartNeeded) {
                Write-Warning '组件要求重启，配置尚未完成。请先告知 Agent，重启后重新执行整块代码。'
                return
            }
            $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
        }
        if ($cap.State -ne 'Installed') { throw '组件状态不是 Installed，请把完整输出发给 Agent。' }
    }
    if (-not (Get-Service -Name sshd -ErrorAction SilentlyContinue)) {
        throw '组件已安装但没有 sshd 服务，请把完整输出发给 Agent。'
    }

    Write-Host '[2/4] 设置开机自启并启动 Windows SSH 服务……'
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
        $svc | Select-Object Name,State,StartMode,ProcessId | Format-Table -AutoSize
        Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {
            $_.LocalPort -eq 22 -or ($svc.ProcessId -gt 0 -and $_.OwningProcess -eq $svc.ProcessId)
        } | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
        throw 'sshd 尚未以自动服务监听可远程访问的 TCP 22。请把输出发给 Agent，检查服务日志、Port/ListenAddress 和端口占用；不自动覆盖已有配置。'
    }

    if ($lan.Count -eq 0) { throw '没有可用的网卡 IPv4，请先检查网线、Wi-Fi 或 DHCP，再重新执行。' }
    Write-Host '[3/4] 创建或修复 TCP 22 的局域网入站规则……'
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

    Write-Host '[4/4] 本机检查通过。可以关闭此窗口；接下来由 B 验证实际 SSH 登录。'
    $svc | Select-Object Name,State,StartMode,ProcessId | Format-Table -AutoSize
    $listen | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
    $rule | Select-Object Name,Enabled,Direction,Action,Profile | Format-Table -AutoSize
    Get-NetFirewallProfile -PolicyStore ActiveStore | Select-Object Name,Enabled,AllowInboundRules,AllowLocalFirewallRules | Format-Table -AutoSize
    Write-Host 'A 的当前 IPv4（多网卡时让 Agent 选择与 B 可达的地址）：'
    $lan | Select-Object InterfaceAlias,IPAddress | Format-Table -AutoSize
    Write-Host '当前账户：'
    whoami.exe
    Write-Host '重启后服务会自动启动，但睡眠/关机、IP 变化、网卡故障或组织策略仍会影响连接。'
}
