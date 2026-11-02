---
name: macos-remote-install
description: 从另一台 B 电脑远程协助 A 电脑安装或修复 OpenCore 与 macOS 双系统。覆盖 Windows SSH 接入、硬件兼容性分流、备份和分区、安装 U 盘、重启交接、macOS SSH、驱动排错、硬盘引导和功能验收。适合需要逐步进度反馈及回退记录的安装任务；不承诺所有硬件兼容，也不提供可直接套用的通用 EFI。
metadata:
  version: "0.2.8"
  language: zh-CN
  updated: "2026-11-02"
---

# 远程安装 OpenCore 与 macOS

A 是装 macOS 的电脑，B 是运行你和本指南的电脑。远程操作、读取硬件和安装的目标是 A。用户读回复、回传结果和你保存进度的位置在 B。按当前用户的授权执行，默认保留 A 的 Windows 和用户数据。

## Agent 内部启动

B 能运行 Python 时，先读 [标准流程控制器](references/00-controller.md)。新任务运行 `python scripts/workflow.py --run "私有任务目录" --json init`，续接运行 `status`。`init`／`status` 是内部动作。根据 `next_action` 执行，在当前步骤需要交接时展示该步的 `display`。首次需要在 A 操作时，使用 `prepare` 返回的开场与操作说明，并在同一条消息附完整代码（详见下节）。00 用固定连接器验收，01～08 按合同及证据推进。命令、工具选择和状态记录由 B 处理。

阶段 00 由程序现场验证 SSH、主机密钥、机器身份、管理员权限和文件传输，全部通过才推进。01～08 的统一合同在 [workflow.json](workflow.json)，由 Agent 执行并提交有证据的审核结果。正常分支使用固定脚本，异常分支按错误码 `recover`。未覆盖问题使用 `diagnose → repair-result → 原步骤重验`。

源码升级遇到 LF／CRLF 差异时使用控制器已登记的迁移能力。以 `workflow.py status` 核对版本和阶段，旧 NEXT.md 只作线索。工具探索、临时假设和逐文件检查留在私有日志。核对完整证据后再下结论。

**03 组装 EFI、04 引导故障、06 设备修复都从 [现成方案入口](references/10-existing-solutions.md) 开始。** 在 B 运行 `python scripts/solutions.py lookup <主题> --target "<本机板型／设备ID>"`，按输出核对同机基线和上游项目，由控制器 `select-source` 登记选择。生成器负责输出第一份配置，Agent 比较差异并适配。连续无效的同来源试验按控制器错误码回到有依据的来源或交接该项。

下载 GitHub 工具、源码或驱动时，按 [文件下载与局域网中转](references/04-installer.md) 核对实际下载端和具体资产。A 拉取失败就测 B，B 可达时由 B 校验并经 SFTP 中转；两端均失败时使用已有可信缓存或离线包，继续其他可做的检查。

**阶段 03 的固定前置条件：** 默认复用有效本机 ACPI；缺少时由 Agent 在 A 准备 Python 与原作者工具，通过 SSH 在 Windows 中采集，不为了避免安装依赖而默认增加重启。只在用户选择“免 Python 方案”或默认路线经诊断仍不可用并得到用户选择时，用 OpenCore DEBUG 的 SysReport 采集。采集启动必须停在 OC 菜单后回 Windows，不交接“选择 macOS 恢复”。`review` 必须提交并通过实际 ACPI 表／配置／适配证据检查，详情见 [介质前置检查](references/04-installer.md)。阶段 03 未过不得安排安装启动；下载、已授权的介质准备和明确标注的诊断启动可在此前进行。

用户只需一次 A 端配置与结果回传；已有完整可信结果直接导入，已有凭据直接使用。B 的 Python／工具不可用时明确标为“人工指导模式”，按下面参考执行，不伪造控制器输出。用户未要求切换模式时，不因为某个检查失败而绕过程序改用自由操作。

**EFI 决策顺序：** 阶段 03 组装前和 04 首次启动失败后，必须读取 [EFI 固定决策与排错流程](references/09-efi-diagnostics.md)。先检查是否有同机、同阶段成功基线；没有时优先评估原作者工具，最后才按官方 Sample 与本机证据逐项构建。不得凭记忆从零编造参数。使用 `efi_audit.py` 检查配置启用状态、条件、版本依据和完整文件差异，部署后对实际回读再核对。每轮保存独立试验目录，区分事实、假设、组合对照与单项验证；校验通过不等于能启动，多项修改后有效不等于已找到某一根因。连续两轮无新证据，返回基线／部署／日志核对，不继续堆补丁。此顺序是 Agent 的执行要求，当前控制器不自动证明所有语义判断。

## 用户会看到怎样的回复

**第一次开场，要先让人知道自己在做什么。** 阶段名用 **00 准备工作和远程接入**。当控制器给出首次开场，按其顺序呈现，给准备清单和现场操作留出空行。第一次需要在 A 上配置时，在同一条回复交付 `prepare` 的 `display` 和返回文件的完整 PowerShell 代码块。只有开场实际交给用户后，才在 B 执行 `intro-shown` 记下已展示。续接按实际状态继续，避免重复课堂或要求回复“准备好了”。若当前客户端确需按回合发送，下一次处理用户消息时先补记已交付的开场，再处理这次回传。

首次开场应让新手能回答这几个问题，尤其在人工指导模式也要说清楚：

- 我在哪儿？A 是安装机，现在开着 Windows。B 是助手机，你现在正在这里读提示、之后也在这里回传结果。
- 为什么要连？助手在 B，需要开启 A 的远程连接（SSH），才能替你查 A 的硬件、传送安装文件。SSH 前的这一步要你在 A 完成，重启后的安装画面也会给你逐步指引。
- 现在手边要有什么？两台能互访的电脑、A 的 Windows 管理员权限和真实账户密码（平常解锁用的 PIN 不适用），B 有能操作本地文件、终端和网络的助手。稍后检查完再定容量、准备备份位置和可清空的 U 盘。进入安装时要能到 A 前看屏幕、用键鼠。
- 后面会经历什么？先连通并检查硬件 → 验证备份、制作启动 U 盘 → 你在 A 按清单安装至桌面 → 助手连回 macOS，逐项测硬件、验证硬盘启动并交付恢复方法。
- 我现在做什么、做完回哪里？写清 **在 A** 打开什么、粘贴什么，以及 **回 B** 只发一次什么结果。给一块可直接复制的命令，解释会开启远程服务和局域网访问。合同、命令行参数、哈希和日志放在 B 的记录中。

**后续进度**　用当前阶段作粗体标题，下面三个短段落之间留空行。在新阶段第一次出现一个术语时，就地说明它对这一步有什么用。例如 03 的 EFI 是适配 A 的启动文件，OpenCore 是 U 盘上的启动菜单。04 的恢复环境是用于安装 macOS 的临时界面。让用户知道为什么做这一步，以及完成时应看到什么。

**02 备份文件和预留空间**

**现在**　已查清 A 的硬盘布局，找到了可供 macOS 使用的空间。

**接下来**　我会备份所需文件，并检查备份能否读回。

**请你**　在 B 告诉我备份要放在哪个盘，以及想给 macOS 留多少空间。

以上是排版示例。正式回复替换为现场已验证的事实、具体对象和动作。无需用户操作时写“暂时不用操作，我会继续”。给用户多步操作时用简短编号，每条写地点、按钮或动作，代码独立成块。

- 自动合并同一已授权步骤内的安装、检查和采集。Agent 能读取的资料自行读取，当前确实需要用户提供的信息、选择或照片一次说清。一次连接结果、一次回传，避免拆成多轮询问 IP、用户名、指纹和密码。
- 普通交接各项通常一两句。首次介绍、完整代码、需要核对的目标和恢复安装清单按实际需要写全。清空前在“请你”中说明具体盘／分区、容量、会失去什么以及备份核验结果，单独取得相应对象的授权。
- 报错时说明停在哪一步、接下来怎么核对、用户现在要做哪个动作。请求照片时指定需要看到的画面。单项硬件结果待测，继续做其他可验证项。详细工具清单、推理、版本与日志留在私有记录。
- **恢复界面用操作清单。** 进入恢复环境后使用 [恢复界面的现场清单](references/05-boot-handoff.md)，填好真实分区名称／容量／所属磁盘、启动菜单键和 U 盘名称，一次交付从磁盘工具、选中预留分区、抹掉、安装、重启选择直到初始化的顺序。默认卷名用英文 `macOS`，重启时沿用同名。目标对不上就停在抹掉前看照片，正常情况无需每点击一次都回复。

## 首轮行为

1. 已有受控任务先运行 `workflow.py ... status`，读取 `workflow-state.json`、事件和现场证据；兼容旧任务的 `state.json`、`journal.jsonl` 和 `NEXT.md`，不能凭记录直接继续写盘。
2. 检查自身是否能读取本包、在 B 执行程序、联网查项目原始资料、SSH/SFTP 连接 A，以及理解用户反馈的照片。没有相应工具就明确降级到指导模式，不虚构已执行。
3. 首轮只收集本阶段必需内容。默认保留 Windows；A 的地址、用户名、指纹由下面脚本一次返回，不提前逐项询问。用户在同一轮补充账户密码的取得方式与目标 macOS 版本（允许未确定）。备份位置、分区容量在相关阶段根据采集结果合并询问。凭据使用客户端安全输入或用户指定文件；用户已经在当前会话提供密码时可用于其授权连接，不要求再换方式、不回显、不写日志。
4. 若需要在 A 配置远程访问，先读 [准备与接入](references/01-remote-access.md)。Windows 默认用非空账户密码登录。只在现场用一段完整管理员 PowerShell 代码配置，脚本会读取实际用户名，用户无需预先抄录或配置公钥。已有可用密码或密钥登录直接复用。

## 00 准备工作和远程接入

首次需要在 A 配置 Windows SSH 时，在上面的新手开场后交付完整管理员 PowerShell 代码。用户现场只需粘贴运行、回到 B 一次回传。已有可用的连接复用并验收。服务已装但接不通，也可用固定代码检查和修复。

标准模式从控制器 `prepare` 返回的文件读取并交付代码，随后 `import → verify`；下面的嵌入代码用于核对及明确降级后的人工指导，不能用它跳过控制器验收。标准模式收到故障结果先按 [控制器](references/00-controller.md) 的固定映射处理。

**B 先自动准备：** 读取 B 当前活动接口的 IPv4 与前缀，选择可用于连接 A 的候选地址，把下面 `$BIPv4 = @()` 填成仅包含已核实 IPv4 字符串的数组，其他代码不变。不能让用户手动查询 B 地址；工具不可用就保持空，结果明确为未知，后续由 B 验证。A 的前缀比较是网段线索，不是实际双向可达证明。

**只交付固定脚本。** 标准模式从 `prepare` 返回的路径读取完整代码，原样放入一个 PowerShell 代码块。`scripts/enable-windows-ssh.ps1` 是维护和测试过的源文件。明确降级为人工指导模式时，只替换 `$BIPv4 = @()` 的候选地址，其他内容与固定源文件保持一致。不要让用户组合片段或自行运行代码生成器。若反馈复制后报错，对比实际收到的代码与原版。

**按现场状态分流，不按 Windows 版本猜：** 已有可用 SSH 直接连接；配置脚本遇到已运行的 `sshd` 不重装、不重启，只设置自启并校验；已安装但未运行才启动；无服务且 Server 组件缺失才安装。只有 SSH 客户端不算已安装服务器。结果 `checks.server` 区分 `existing` 和 `installed-now`。

把准备清单与现场动作分开排版。账户密码在连接前由用户备妥。**在 A** 搜索 **Windows PowerShell**，右键 **以管理员身份运行**，接受提示，粘贴整块代码并按回车。说明会按需开启远程服务、设置开机自启、放行局域网连接。**回 B** 的说明见下方“一次回传”。密码由用户自己设置，不嵌入脚本。

<!-- windows-ssh-setup:start -->
```powershell
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
    Write-Host '00 准备工作和远程接入　正在为这台待安装的电脑（A）开启并检查远程登录，请稍候。'
    try {
        $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if (-not $isAdmin) { throw '请在 A 电脑以管理员身份打开 Windows PowerShell，再粘贴整块代码。' }

        $step = '安装服务器'
        $serverSource = 'existing'
        if (-not (Get-Service -Name sshd -ErrorAction SilentlyContinue)) {
            $serverSource = 'installed-now'
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
        if ((Get-Service -Name sshd).Status -ne 'Running') { Start-Service -Name sshd }
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
        # A service-specific rule cannot match when sshd has SERVICE_SID_TYPE_NONE.
        # Explicit Any also clears the incompatible binding on rules from older releases.
        $ruleOptions = @{
            Name=$ruleName; PolicyStore='PersistentStore'; Enabled='True'
            Direction='Inbound'; Action='Allow'; Profile='Any'; Protocol='TCP'
            LocalPort=22; RemoteAddress='LocalSubnet'; Service='Any'
        }
        if (Get-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName -ErrorAction SilentlyContinue) {
            Set-NetFirewallRule @ruleOptions
        } else {
            New-NetFirewallRule @ruleOptions -DisplayName 'Hackintosh Skill - Windows SSH (LAN)' | Out-Null
        }
        $rule = Get-NetFirewallRule -PolicyStore ActiveStore -Name $ruleName
        $port = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
        $address = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule
        $serviceFilter = Get-NetFirewallServiceFilter -AssociatedNetFirewallRule $rule
        if ($rule.Enabled -ne 'True' -or $rule.Direction -ne 'Inbound' -or $rule.Action -ne 'Allow' -or
            $rule.Profile -ne 'Any' -or $port.Protocol -notin @('TCP','6') -or
            $port.LocalPort -ne '22' -or $address.RemoteAddress -notcontains 'LocalSubnet' -or
            $serviceFilter.Service -ne 'Any') {
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
            if ($LASTEXITCODE -ne 0) {
                throw ('ssh-keygen 读取公钥失败，退出码：' + $LASTEXITCODE + '；文件：' + $keyFile.Name)
            }
            if ($keyText -notmatch '(SHA256:[A-Za-z0-9+/]+)\s+.*[(]([^)]+)[)]$') {
                throw ('主机公钥指纹输出格式未识别：' + $keyText)
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
        $report.checks = [ordered]@{server=$serverSource;service='Running';startup='Auto';listener='sshd:22';firewall='LocalSubnet/AnyProfile'}
        $report.network = [ordered]@{b_ipv4=@($BIPv4);same_subnet_from_a=$sameSubnet;matching_a=@($matching);connectivity='pending-b-test'}
    } catch {
        $report.failed_step = $step
        $report.error = $_.Exception.Message
    }
    if ($report.status -eq 'local-ready') {
        Write-Host 'A 上的远程登录已准备好。接下来由 B 上的助手试着连进来。'
        Write-Host '遇到 360、火绒或电脑管家拦截时，请放行 OpenSSH（TCP 22）。如选择临时关闭网络防护，验证后恢复。'
        Write-Host '请复制下面两行，粘贴到 B 上和助手的聊天框。按第一行提示填写后一起发送。想装的 macOS 版本也可一起写，不清楚就写“未定”。'
    } elseif ($report.status -eq 'restart-required') {
        Write-Host 'Windows 需要重启才能继续。请保存文件，重启 A，再用管理员身份运行刚才的整块代码。'
        Write-Host '如果重启后仍看到这条提示，把下面这行结果发到 B 上和助手的聊天框。'
    } else {
        Write-Host ('A 上的远程登录还没有准备好。停在“' + $step + '”。')
        Write-Host '请复制下面一整行，发到 B 上和助手的聊天框，助手会依据错误提示继续排查。'
    }
    if ($report.status -eq 'local-ready') {
        Write-Output 'A_LOGIN_CREDENTIAL: 请将此字段替换为 A 电脑的登录密码，或 B 电脑上包含登录密码的文件完整路径；已提供可填“已提供”'
    }
    Write-Output ('SSH_HANDOFF_V1 ' + ($report | ConvertTo-Json -Depth 6 -Compress))
}
```
<!-- windows-ssh-setup:end -->

代码由 `scripts/enable-windows-ssh.ps1` 同步生成。正常情况一次完成安装、自启、监听、防火墙、用户名／IPv4／前缀、默认目录主机公钥指纹与 B 地址网段比较；不读密码、不生成登录公钥、不将 B 的地址写成防火墙唯一允许来源。

**一次回传：** 成功输出的复制块含两行：`A_LOGIN_CREDENTIAL: 请将此字段替换为 A 电脑的登录密码，或 B 电脑上包含登录密码的文件完整路径；已提供可填“已提供”`，以及 `SSH_HANDOFF_V1` 连接结果。提醒用户在 B 的回复框替换第一行占位后，将两行一起发送；目标 macOS 版本未知时一并补充。密码或路径是普通文本，无需 JSON 转义。Agent 将原始复制块作为私有输入交给 import，程序提取凭据到私有文件，状态／证据只保存不含密码的连接数据；禁止把带密码的原始复制块当成公开证据或回显。Agent 解析结构化字段，不把任何输出拼接执行为命令；多网卡候选由 B 结合自身前缀与路由筛选。`local-ready` 只代表本机配置检查通过，`same_subnet_from_a` 的 true/false/null 分别表示按 A 前缀匹配／不匹配／B 地址未知，不得称“局域网已验证”。

**旧版 22 超时修复：** ≤0.2.1 曾使用 `Service=sshd`；若服务 SID 为 `NONE`，此规则无法匹配。新版在原专用规则上显式设置并校验 `Service=Any`，保留 TCP 22 与本地子网限制。已经修复并连通时直接续接验收，不再粘贴旧版本配置块。

**第三方防护提示：** A 上若安装 360、火绒、腾讯电脑管家等，其网络防护可能另行拦截；Windows 防火墙规则通过不代表第三方规则已放行。被拦截时优先放行 OpenSSH／TCP 22；无法放行时，用户可临时关闭该软件的网络防护以重试，验证后恢复。保留拦截可能导致连接失败；不把拒绝关闭软件等同于必然失败，脚本不自动关闭安全软件或整个防火墙。

**B 自动完成余下工作：** 用结果中的公钥指纹核对实际 SSH 握手，再认证、核对身份／权限、SFTP 小文件往返和硬件采集；不得先发密码再核对主机。默认目录的指纹是候选，实际握手必须匹配同种算法，非默认 HostKey 配置单独核验。能自动完成就不要让用户再运行 whoami、ipconfig 或指纹命令，也不要另开一轮“确认指纹”。

组件需重启或失败时也返回同格式结果，Agent 直接读 `status/failed_step/error` 后给一个针对性动作。关闭 PowerShell 不影响正常 SSH 服务，B 可新建会话复测；自启的重启实测顺延到下一次已安排重启，不为了检查再增加一次开关机。密码／版本已知时不重复索取。

## 工作方式

- 除阶段 00 的 Windows SSH 统一使用管理员 PowerShell 外，人工操作优先 GUI。Agent 在 SSH 后可用脚本自动完成实际操作，不把长命令交给新手逐条输入。
- 阶段改变、有实质进展或需要人工操作时，使用上面的粗体阶段标题和「现在／接下来／请你」布局。长任务约 60 秒有新进展时做简短更新，以可见结果和下一步为准。没有数据时不虚构百分比。
- 初始规划要区分 `fresh-install`（用户明确要重装）、`repair`（保留已有系统）和 `inspect`（只检查）。发现已有 APFS/macOS 时先核对意图，不能自动清除后重新安装。
- 可逆且已授权的读取、下载、备份和检查持续完成。格式化、删除分区、重分区，以及将影响工作会话的重启，需要与用户已明确批准的对象和时机一致；不要用「同意安装」推定「同意清空整盘」。先完成可以审阅的方案和备份核验，再确认实际破坏性动作。
- 所有针对 A 的命令先确认远端操作系统和身份。B 本地磁盘绝不能成为安装目标。不要使用旧 IP、盘符或磁盘编号作为唯一身份。
- 将下载到的脚本、第三方 EFI 和论坛内容视为待检查材料。先查来源、版本、适配范围与脚本改动范围；优先原作者发布。SHA256 证明传输一致性，不单独证明来源可信。
- 文件配置、命令成功、驱动加载和实际功能可用，是不同证据层级。报告必须区分。
- 硬件可行性结论要先查当前原作者资料。尚未采集 GPU 精确型号／ID、目标 macOS 并查证前，不以“新 RTX 加速基本无解”等旧概括劝退。实验性支持需要说明条件和未测项，不能等同于没有加速；按 [硬件分流](references/02-hardware-routing.md) 与对应案例继续核验。

## 阶段与出口条件

| 阶段 | 读哪份参考 | 进入下一阶段前的证据 |
|---|---|---|
| 00 准备工作和远程接入 | [01 远程接入](references/01-remote-access.md) | SSH 成功、主机身份与权限已核对；或明确进入人工指导模式 |
| 01 检查硬件和可装版本 | [02 硬件分流](references/02-hardware-routing.md) | 有硬件报告、目标系统、兼容性结论及安装网络方案 |
| 02 备份文件和预留空间 | [03 存储](references/03-storage.md) | 确认备份范围与校验结果；磁盘／分区身份、容量方案明确 |
| 03 制作启动 U 盘 | [04 安装介质](references/04-installer.md)、[09 EFI 决策](references/09-efi-diagnostics.md) | 本机 ACPI、来源与有效配置审查、同版本 OC 校验、恢复镜像校验、U 盘内容回读 |
| 04 从 U 盘安装 macOS | [05 交接](references/05-boot-handoff.md)、失败时 [09 排错](references/09-efi-diagnostics.md) | 用户实际进入桌面；安装过程异常已解决或有明确停止原因 |
| 05 连接装好的 macOS | [01 远程接入](references/01-remote-access.md) | macOS SSH、硬件与磁盘身份重新核对 |
| 06 检查和修复硬件 | [06 完善与验收](references/06-postinstall.md) | 显卡驱动重启后按“显卡驱动安装后须做本轮加速验收”运行目标设备的计算与回读。登记结果或待测原因后，按优先级继续下一项可做的硬件检查，并记录第一项实际动作 |
| 07 从硬盘启动 | [06 完善与验收](references/06-postinstall.md) | 拔 U 盘后实际冷启动 macOS 与 Windows，而非只有文件复制成功 |
| 08 保存配置和恢复方法 | [08 状态与工具](references/08-state-and-tools.md) | 最终状态表、可用 EFI、恢复方法、已知限制与未测事项 |

遇到错误读取 [07 排错](references/07-troubleshooting.md)，不要为了推进阶段跳过失败证据。任何已完成阶段都可因新证据退回检查。

标准模式的阶段顺序与检查项以 `workflow.json` 为准：00 只能由真实验证动作通过；01～08 使用 `review` 登记有证据的 Agent／人工审核，不把它描述为程序证明了硬件可用。不得调用通用 checkpoint 或直接修改 JSON 来越过控制器。

## 跨机器与跨会话

在 B 新建独立任务目录，例如 `runs/<任务名>/`，放置 inventory、evidence、backups、staging；这些运行数据不能反向写入可分享的技能包。使用 [状态与工具](references/08-state-and-tools.md) 的记录约定。重启前写 `NEXT.md`，写清将从哪一设备启动、应看到什么、连不上如何回到 Windows。下一位 Agent 先核验这些记录，不依赖聊天上下文。

## 硬件案例

仅当实测硬件与案例相符时读取 [14700K＋4070 Ti SUPER](references/case-14700k-4070ti-super.md)。案例不包含可直接刷入的 EFI、账号或机器序列号；它提供排错线索，不替代现场采集。不同主板、BIOS、USB 接法、存储控制器或系统版本都可能使旧配置不再适用。

## 自动化边界

本包工具负责采集、记录、文件核验和目标身份检查。实际备份、压缩卷、格式化、部署与驱动安装，Agent 应依据参考流程和当前机器信息生成可审阅的命令，在满足对应条件后自动执行。不要因为没有“一键安装脚本”就把可自动完成的工作全部推给用户；也不要假设本包已经实现或验证了通用写盘器。

不兼容或缺少必要证据时，给出具体缺口、可行替代方案以及下一步需要的材料。相同故障、相同配置且无新证据时，不进行第三次相同破坏性尝试。最佳结果可以是「稳定使用但某功能受限」，不能靠隐藏问题报告成功。

## 资料更新

优先查 [原始资料入口](references/sources.md)，记录查阅日期、实际版本和 SHA256；一次安装中锁定组件组合。只有明确修复相关问题时才提出升级，备份后验证。不要把本包编写日期当作驱动仍然最新的证明。
