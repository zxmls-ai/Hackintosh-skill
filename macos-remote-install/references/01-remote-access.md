# 01 远程接入与机器身份

## 先在 B 检查能力

可选运行 `python scripts/agentkit.py preflight`（工作目录为技能目录，Python 3.10+）。这只检查 B 的工具，不扫描或修改 A。测试真正的 Python 执行能力，Windows 的 python.exe 可能只是商店入口。

至少需要：本地文件与终端、SSH/SFTP、HTTPS 下载。看图能力用于处理 BIOS／启动报错；没有时请用户转录关键文字或使用可用的图像工具。Python 不存在时可用 PowerShell／系统工具完成等价检查；不得假装调用成功。B 为 macOS 或 Linux 时沿用同样流程，替换本地命令语法，A 的 Windows 命令仍由远端 PowerShell 执行。

优先使用客户端已有 SSH 连接器或系统 SSH。禁止为本任务关闭 B/A 的整个防火墙或绕过客户端审批。两台电脑先保持同一可达局域网；远程跨网时需要用户已有且授权的 VPN 或其他连接，不能擅自做公网端口转发。

## A 是 Windows：先给用户 GUI 指引

一次给出当前需要的几个步骤；用户已经配置 SSH 时直接验证，不要求重做。

1. 开始菜单搜索“可选功能”，进入设置，选择添加／查看功能，安装 **OpenSSH Server／OpenSSH 服务器**。只安装 Client 不会出现 sshd 服务。Windows 版本导致入口变化时使用设置搜索。
2. 开始菜单搜索“服务”，找到 **OpenSSH SSH Server**，设为“自动”，点击启动。没有该服务先确认服务器组件安装完成，不重复 Start-Service。
3. 打开“设置→网络和 Internet”，查看当前有线网络 IPv4 地址。用户提供 A 的地址、Windows 实际账户名和登录方式。Windows Hello PIN 通常不能代替账户密码。
4. 由 B 检查 TCP 22 和 SSH。连接失败区分：超时（网络／防火墙）、拒绝（无监听）、认证失败（账户／密钥）、权限不足；不要靠不停换密码排错。

微软原始说明：[安装与启用 OpenSSH](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse)。可选功能缺失或安装报错时，在 A 本机管理员终端确认组件状态和系统服务；如需命令，只给短且能解释的必要操作，不从不明镜像下载 sshd。

服务安装通常附带入站规则。若规则缺失，创建专用于 SSH 的规则并按实际需要限定 B 地址与网络配置文件；不修改已有无关规则。需要修改规则前先记录现状。

## B 建立连接后

- 第一次连接核对 A 在本机显示的 SSH 主机公钥指纹；把 Windows 与 macOS 主机密钥分别保存，不全局禁用校验。换系统导致相同 IP 出现不同主机密钥时，核实后使用独立 SSH Host 别名／记录，不直接忽略警告。
- 先执行无副作用的身份检查，例如远端 `hostname`、Windows 系统信息和 `whoami`；记录 A 的物理硬件身份。检查当前远程会话的管理员权限，不因账户名是 Administrator 就假设已获得所有权限。
- 上传并通过远端 PowerShell 运行 `scripts/collect-windows.ps1 -OutputPath <A上的报告绝对路径>`。建议通过 SFTP 上传脚本而非拼接复杂引号。Windows PowerShell 5.1 脚本文件需保留包内 UTF-8 BOM。
- 从 A 取回 JSON 后读取 `errors`。采集失败的字段是未知，不是“不存在”。获取报告只是第一步，仍需 ACPI、USB 端口与显示连接等后续采集。
- 优先建立经用户授权的 SSH 密钥认证，以便 Agent 非交互运行。私钥留在 B 的受控位置；不放入可分享包。Windows 管理员账户的 authorized_keys 位置与权限按[微软公钥认证说明](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)处理，不照抄 Linux 路径。
- 若 Agent 无安全密码输入渠道，请用户在自己的终端完成首次密钥配置，或使用其指定的本地凭据机制。不把密码拼入进程命令行、日志或聊天。
- SSH 的 GUI 程序可能运行在用户看不见的会话。优先 CLI；确实只能 GUI 时交给用户操作或使用明确可用的桌面控制工具，不无限重复启动程序。

## A 是 macOS：安装后重新接管

给用户 GUI 步骤：系统设置→通用→共享→远程登录，启用并允许指定管理员。需要读取受保护日志／文件时再说明并启用“允许远程用户对磁盘进行完全访问”。系统设置→网络查看当前 IPv4。

屏幕共享可作为辅助：通用→共享→屏幕共享；SSH 已足够处理大多数检查。跨平台 VNC 需要客户端支持相应认证，必要时由用户在该设置中启用 VNC 密码；不强制开放“所有人”。[Apple 远程登录说明](https://support.apple.com/guide/mac-help/allow-a-remote-computer-to-access-your-mac-mchlp1066/mac)

B 验证新 SSH 指纹后运行 `sw_vers`、`uname -m`、`diskutil list physical`，核对物理磁盘、网卡身份及用户确认。OpenCore 会伪装部分主板／系统身份，Windows 的 SMBIOS UUID 不能直接当作 macOS UUID；跨系统关联优先物理磁盘身份、GPT 分区 GUID、网卡及现场确认。

上传 `collect-macos.sh`，以 `sh collect-macos.sh <A上的新诊断目录>` 运行。需要完整日志时按授权使用 sudo，密码经 stdin／终端输入，不写到脚本。取回诊断目录。Mac 未装 Python 不影响该脚本。

## 断线处理

预期重启时保存检查点，按合理间隔探测已确认地址，不高频重试。地址失效请用户提供新地址或查已授权的 DHCP 记录。重启后只有网络可达不代表仍是 A；再次校验主机密钥和硬件身份。不得对整个网段自动尝试用户凭据。
