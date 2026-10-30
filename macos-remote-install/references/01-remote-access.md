# 01 远程接入与机器身份

## 先在 B 检查能力

可选运行 `python scripts/agentkit.py preflight`（工作目录为技能目录，Python 3.10+）。这只检查 B 的工具，不扫描或修改 A。测试真正的 Python 执行能力，Windows 的 python.exe 可能只是商店入口。

至少需要：本地文件与终端、SSH/SFTP、HTTPS 下载。看图能力用于处理 BIOS／启动报错；没有时请用户转录关键文字或使用可用的图像工具。Python 不存在时可用 PowerShell／系统工具完成等价检查；不得假装调用成功。B 为 macOS 或 Linux 时沿用同样流程，替换本地命令语法，A 的 Windows 命令仍由远端 PowerShell 执行。

优先使用客户端已有 SSH 连接器或系统 SSH。禁止为本任务关闭 B/A 的整个防火墙或绕过客户端审批。两台电脑先保持同一可达局域网；远程跨网时需要用户已有且授权的 VPN 或其他连接，不能擅自做公网端口转发。

## A 是 Windows：先账户，再服务器，再连接

一次给出当前需要的几个步骤，并说明在 A 还是 B 操作。已经能连接的 SSH 直接复用并核对身份，不要求重装或更换认证方式。

### 00-1 先确认账户与登录方式

默认以 **Windows 实际账户名＋账户密码** 完成首次接入，公钥不是前置条件。用户已有可用密钥或明确选择公钥时沿用其选择。[微软文档确认 Windows OpenSSH 支持 password 与 publickey](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh-server-configuration)。

在开始安装 SSH 前告诉用户：

1. 采用密码登录时，A 的账户应有**非空账户密码**。平时自动登录、使用 PIN 或指纹，并不证明自己知道账户密码；Windows Hello PIN 不能填进 SSH 的密码提示。这个条件针对密码登录，不代表所有密钥登录都要求先设置密码。
2. 本地账户没有密码：在 A 的“设置→账户→登录选项→密码→添加”设置，由用户自己输入。已有密码则不改。入口缺失时先确认账户类型，不关闭空密码限制来绕过。[空密码限制说明](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/security-policy-settings/accounts-limit-local-account-use-of-blank-passwords-to-console-logon-only)
3. 确认实际用户名，不用桌面的显示昵称猜测。必要时让用户在 A 的终端运行 `whoami`；安装服务及后续磁盘操作需要管理员权限，但“SSH 能登录”和“远程会话能管理磁盘”仍分开验证。
4. Microsoft 在线账户／仅 Hello 登录／组织账户需要先确认是否有可用于 SSH 的账户凭据。失败时按账户类型查证，不假设电子邮件地址必然是 SSH 用户名；Entra 账户认证不受 Windows OpenSSH 支持。需要独立本地管理员时，说明用途并在用户同意后通过“设置→账户→其他用户”创建，不擅自替换现有账户。

密码通过客户端凭据输入或用户指定的本地凭据文件交给 B；Agent 可以在内部读取并调用支持密码的 SSH 库／连接器，不回显内容、不把密码放在进程参数里。不要把“不要将密码写进聊天或日志”误读成“只能使用公钥”。

### 00-2 统一使用管理员 PowerShell

直接向用户展示 [SKILL 主入口](../SKILL.md) 的完整配置代码，并说明在 A 搜索 Windows PowerShell、右键以管理员身份运行、粘贴整块并回车。阶段 00 不再走可选功能／services.msc，也不把“GUI 优先”套用到这一步。代码源为 `scripts/enable-windows-ssh.ps1`；Windows PowerShell 5.1 的脚本文件使用 UTF-8 BOM。

脚本依次显示四步进度：安装检查 → 自动启动和监听检查 → 防火墙配置 → 本机结果。实际改动仅限安装缺失的 OpenSSH Server、sshd 启动类型与启动操作、名为 `Hackintosh-Skill-SSH-In-TCP` 的专用入站规则。已安装服务不叠装，已有会话不主动重启，用户名／密码与 sshd_config 不自动修改。[微软服务安装与自启说明](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse)

| 结果 | 下一步 |
|---|---|
| 无 sshd，Server 状态 NotPresent | 脚本安装组件，重新检查状态，继续配置 |
| 已存在 sshd 服务 | 直接配置自启与检查实际监听，不安装第二套 |
| RestartNeeded=True | 当前配置未完成；记录后安排重启，再运行整块 |
| Installed 但无服务／状态未知／安装报错 | 停止并读取错误，不反复 Start-Service |
| 服务运行但只有其他端口、回环地址或 22 被其他进程占用 | 输出服务与端口信息；Agent 查实际配置、日志和占用，不覆盖用户已有 SSH 配置 |
| 防火墙写入／读回失败 | 当前配置未通过，检查管理员权限、有效策略与错误，不关闭防火墙 |

安装进度不是安装完成。遇到 0x800f0954、0x800f081f 等错误或长时间无进展，保留错误并检查 Windows Update／WSUS／FoD 来源，不承诺终端命令必定成功。按[微软故障说明](https://learn.microsoft.com/en-us/troubleshoot/windows-server/system-management-components/cant-install-openssh-features)选择匹配版本的源；组件途径不可用时，再评估微软维护的 [Win32-OpenSSH 发布包](https://github.com/PowerShell/Win32-OpenSSH/releases)，核对架构、版本及安装说明。不要混装、关闭组织策略或下载不明整合包。

### 00-3 验证服务、监听与防火墙持久配置

- `Set-Service -StartupType Automatic` 让服务随 Windows 启动；`Start-Service` 立即启动。不要手工运行 `sshd.exe -D` 或依靠终端后台作业替代 Windows 服务。关闭 PowerShell 不会结束正常的 sshd 服务。
- 必须核对 22 的 `OwningProcess` 等于 sshd 服务进程，并且绑定通配地址或当前网卡 IPv4；不能仅看服务 Running 或任意进程占用了 22。旧服务若使用自定义端口，按实际意图适配监听与防火墙，不能强行抢占 22。
- 脚本写入 `PersistentStore`，再从 `ActiveStore` 读取专用规则并检查方向、动作、端口与地址范围。规则使用 `Profile Any` 和 `RemoteAddress LocalSubnet`，支持公用／专用／域网络与同子网 DHCP 地址变化。原有其他规则不被改动，因此也不能声称整个系统只开放了本地子网。[防火墙规则参数](https://learn.microsoft.com/en-us/powershell/module/netsecurity/set-netfirewallrule)
- 跨网段或 VPN 场景需要 Agent 将规则来源适配为 B 的实际地址／授权网段；本地子网规则不保证跨网段连接。显式阻止规则、组织禁止本地规则合并、第三方防火墙、AP 隔离等也可能阻止访问；不能把一条 Allow 规则读回成功当作链路可通。
- 结果输出当前 IPv4 与 `whoami`，由 B 选择可达地址并验证。多网卡、169.254 自动地址、VPN 或默认路由异常先查现场；不要沿用旧 IP。服务自启不固定 IP，需要时可指导用户在路由器给对应网卡做 DHCP 地址保留。

若用户报告“关闭窗口后就断了”，先区分是手工前台 sshd、服务崩溃，还是随后睡眠／断网／IP 变化，不让用户靠保持终端开启来维持连接。若运行中的服务确实反复退出，收集 OpenSSH Operational 和 System 服务控制管理器日志，修复具体原因后再评估服务恢复动作，不用无限重启掩盖错误。

关闭 A 上的 PowerShell 后，B 重新建立独立 SSH 会话并验证身份。后续经用户安排的重启后，再检查新地址、主机密钥、自启和独立登录；没有重启实测时如实记录未测。`Running/Auto` 不代表电脑睡眠或关机时也能响应。

### 00-4 用密码完成真实连接

Agent 优先使用已有 SSH 连接器或支持密码认证的库，通过受控输入／用户指定文件读取凭据。若用系统 SSH 做交互验证，可在 **B** 的终端运行下面的示例，把两个占位内容换成 A 的实际值：

```text
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -l 实际账户名 A的IPv4地址
```

先核对首次连接指纹，再输入账户密码；输入时没有星号或文字是正常现象。这条命令仅对本次连接优先使用密码，不修改 A 的认证配置。用户在另一个终端登录成功，只能证明那条连接可用；Agent 仍需验证自己使用的工具会话。

排错按证据区分：

- 超时：检查地址、链路、端口和防火墙；连接拒绝：检查监听服务；认证失败：检查用户名、非空账户密码、账户限制和 sshd 配置。不把 AUTH_FAILED 简化为“基本是用了 PIN”，也不循环猜密码。
- `Permission denied (publickey)`：检查客户端是否禁止密码（例如 BatchMode）以及服务端实际配置，不直接宣称 Windows 必须用公钥。若服务端被设为仅公钥，按用户选择保留该策略或经授权备份后调整 `%ProgramData%\ssh\sshd_config`；检查全局与 Match 条件，修改后用实际 sshd 的 `-t` 校验再重启服务。
- Agent 的终端不能输入密码：这是工具交互能力限制。先查可用连接器、SSH 库或用户指定的凭据机制；确实都不可用时说明限制，让用户选择人工指导或可选的密钥方案，不能称其为 Windows 要求。

主机指纹用于确认“连到的是否是 A”，与“给用户安装登录公钥”不是一回事。密码登录也要核验主机指纹。默认 Windows 组件可在 A 本机显示指纹：

```powershell
& "$env:WINDIR\System32\OpenSSH\ssh-keygen.exe" -lf "$env:ProgramData\ssh\ssh_host_ed25519_key.pub"
```

仅用于默认路径且该文件存在的安装；自定义来源应查实际工具路径和 sshd HostKey 配置。比较 B 所显示的同种算法指纹，不把主机公钥复制到 authorized_keys。

### 公钥登录是可选优化

仅在用户选择、已有可用密钥，或确认客户端没有可用密码输入机制并取得用户同意后配置。已经能用密码自动执行操作时无需迁移。按[微软公钥认证说明](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)处理管理员账户的 authorized_keys 路径与权限；私钥留在 B。独立验证新连接成功前保留原有可用登录方式，不因生成了密钥就宣布远程接入完成。

## B 建立连接后

- 第一次连接核对 A 在本机显示的 SSH 主机公钥指纹；把 Windows 与 macOS 主机密钥分别保存，不全局禁用校验。换系统导致相同 IP 出现不同主机密钥时，核实后使用独立 SSH Host 别名／记录，不直接忽略警告。
- 先执行无副作用的身份检查，例如远端 `hostname`、Windows 系统信息和 `whoami`；记录 A 的物理硬件身份。检查当前远程会话的管理员权限，不因账户名是 Administrator 就假设已获得所有权限。
- 上传并通过远端 PowerShell 运行 `scripts/collect-windows.ps1 -OutputPath <A上的报告绝对路径>`。建议通过 SFTP 上传脚本而非拼接复杂引号。Windows PowerShell 5.1 脚本文件需保留包内 UTF-8 BOM。
- 从 A 取回 JSON 后读取 `errors`。采集失败的字段是未知，不是“不存在”。获取报告只是第一步，仍需 ACPI、USB 端口与显示连接等后续采集。
- 记录已验证的认证方式及凭据取得机制，不保存密码内容；密码连接与公钥连接均可完成本阶段。阶段出口是 Agent 自身会话成功执行身份检查并完成一次 SFTP 小文件往返核验，或明确告知用户当前仅能人工指导。
- SSH 的 GUI 程序可能运行在用户看不见的会话。优先 CLI；确实只能 GUI 时交给用户操作或使用明确可用的桌面控制工具，不无限重复启动程序。

## A 是 macOS：安装后重新接管

给用户 GUI 步骤：系统设置→通用→共享→远程登录，启用并允许指定管理员。需要读取受保护日志／文件时再说明并启用“允许远程用户对磁盘进行完全访问”。系统设置→网络查看当前 IPv4。

屏幕共享可作为辅助：通用→共享→屏幕共享；SSH 已足够处理大多数检查。跨平台 VNC 需要客户端支持相应认证，必要时由用户在该设置中启用 VNC 密码；不强制开放“所有人”。[Apple 远程登录说明](https://support.apple.com/guide/mac-help/allow-a-remote-computer-to-access-your-mac-mchlp1066/mac)

B 验证新 SSH 指纹后运行 `sw_vers`、`uname -m`、`diskutil list physical`，核对物理磁盘、网卡身份及用户确认。OpenCore 会伪装部分主板／系统身份，Windows 的 SMBIOS UUID 不能直接当作 macOS UUID；跨系统关联优先物理磁盘身份、GPT 分区 GUID、网卡及现场确认。

上传 `collect-macos.sh`，以 `sh collect-macos.sh <A上的新诊断目录>` 运行。需要完整日志时按授权使用 sudo，密码经 stdin／终端输入，不写到脚本。取回诊断目录。Mac 未装 Python 不影响该脚本。

## 断线处理

预期重启时保存检查点，按合理间隔探测已确认地址，不高频重试。地址失效请用户提供新地址或查已授权的 DHCP 记录。重启后只有网络可达不代表仍是 A；再次校验主机密钥和硬件身份。不得对整个网段自动尝试用户凭据。
