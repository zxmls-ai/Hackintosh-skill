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

### 00-2 安装或确认 OpenSSH 服务器

图形入口优先，但不把固定菜单路径当成所有 Windows 的共同前提。Windows 10/11 的“可选功能”可能位于“应用”或“系统”，也可能被精简、受策略限制，或服务器已经安装而不再显示在添加列表。

- 开始菜单搜索“可选功能”，同时检查已安装列表和“添加／查看功能”，目标是 **OpenSSH Server／OpenSSH 服务器**。只看到 Client／客户端不等于服务器已安装。
- 找到服务器就安装；找不到、安装失败或不确定状态时，立即转到下面的短命令检测，不让用户反复寻找不存在的按钮。
- 在 **A 本机**搜索“Windows PowerShell”，右键“以管理员身份运行”。先只执行检测：

```powershell
Get-Service -Name sshd -ErrorAction SilentlyContinue
Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' -ErrorAction Stop
```

按输出分流：

| 结果 | 下一步 |
|---|---|
| 已存在 sshd 服务 | 检查其安装来源与运行状态，直接进入启动／验证；不要叠装第二套 OpenSSH |
| 无 sshd，Server 状态 NotPresent | 执行下面的安装命令，等待最终输出 |
| 状态 Installed，但无 sshd | 安装／服务异常，读取具体错误和系统状态；不反复执行 Start-Service |
| 查询无结果或报错，或出现其他状态 | 获取 winver 的版本／build 与完整错误；检查组件源、精简系统、策略及待重启状态，不自动视为 NotPresent |

仅在确定未安装且在线组件可用时执行：

```powershell
Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' -ErrorAction Stop
```

看到下载进度不是安装完成。安装结束后重新检查组件状态与 sshd 服务；若 `RestartNeeded` 为 True，保存阶段状态并安排用户重启，再验证。安装失败不继续执行服务启动命令。[微软安装说明](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse)

遇到 0x800f0954、0x800f081f 等错误或长时间无进展，保留错误码并检查 Windows Update／WSUS／FoD 来源，不承诺终端命令必定成功。按[微软故障说明](https://learn.microsoft.com/en-us/troubleshoot/windows-server/system-management-components/cant-install-openssh-features)选择匹配系统版本的 FoD 源；系统组件途径不可用时，再评估微软维护的 [Win32-OpenSSH 发布包](https://github.com/PowerShell/Win32-OpenSSH/releases)，核对架构、版本及该包的安装说明。不要混装两种来源、关闭组织策略或下载不明整合包。

### 00-3 启动服务并检查网络

确认服务存在后，可在 A 的“服务”中将 **OpenSSH SSH Server** 设为“自动”并启动。已经打开管理员 PowerShell 时也可用：

```powershell
Set-Service -Name sshd -StartupType Automatic -ErrorAction Stop
Start-Service -Name sshd -ErrorAction Stop
Get-Service -Name sshd
Get-NetTCPConnection -State Listen -LocalPort 22 -ErrorAction SilentlyContinue
Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue
```

状态应为 Running，并确认 sshd 实际监听端口（默认 22，自定义配置按实际端口）。安装一般会创建入站规则；规则不存在、禁用或与当前网络配置不匹配时，先记录现状，按实际需要创建／调整仅用于 SSH 的规则，来源限定 B 的地址，不关闭整个防火墙，不覆盖无关规则。上述命令只检查规则，不会自动修复缺失规则。

A 在“设置→网络和 Internet”查看当前有线 IPv4，或用 `ipconfig`。B 检查到这个地址的实际 SSH 端口，随后尝试认证；端口可达不算 SSH 登录成功。

### 00-4 用密码完成真实连接

Agent 优先使用已有 SSH 连接器或支持密码认证的库，通过受控输入／用户指定文件读取凭据。若用系统 SSH 做交互验证，可在 **B** 的终端运行下面的示例，把两个占位内容换成 A 的实际值：

```text
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -l 实际账户名 A的IPv4地址
```

先核对首次连接指纹，再输入账户密码；输入时没有星号或文字是正常现象。这条命令仅对本次连接优先使用密码，不修改 A 的认证配置。用户在另一个终端登录成功，只能证明那条连接可用；Agent 仍需验证自己使用的工具会话。

排错按证据区分：

- 超时：检查地址、链路、端口和防火墙；连接拒绝：检查监听服务；认证失败：检查用户名、非空账户密码、账户限制和 sshd 配置。不循环猜密码。
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
