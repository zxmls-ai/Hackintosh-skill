# Hackintosh-skill

谁说黑苹果没有通用解，AI不就是吗？将这份指南发送给Codex，Claude Code，DeepSeek Harness，Workbuddy等Agent工具，它会一步一步指引你完成黑苹果安装，并为你调试系统至最佳兼容状态！

让运行在 **B 电脑**上的 Agent，通过远程连接协助 **A 电脑**安装、调试与验收 macOS，保留 Windows。面向小白，把能够自动完成的工作交给 Agent，Windows SSH 用一次粘贴的管理员 PowerShell 配置，其余现场操作优先 GUI。

**v0.1.3：阶段 00 只用 PowerShell，自动配置 SSH 自启、TCP 22 防火墙规则并核验监听。** 提供通用决策流程与检查工具，没有一份适用于所有机器的 EFI。能够评估不同硬件，并在缺少支持时说明限制；不承诺所有电脑都能安装或所有功能完美。实际执行主路线为 x86-64 UEFI PC。

## 给 Agent 一个仓库链接

在 WorkBuddy＋DeepSeek 或具备文件、终端与联网能力的其他 Agent 中，直接发送下面这段话：

```text
仓库：https://github.com/zxmls-ai/Hackintosh-skill

请先读取仓库 README.md，再读取 macos-remote-install/SKILL.md，按它协助我在另一台 A 电脑安装 OpenCore 与 macOS。你运行在 B 电脑。先检查你的工具能力，再引导我配置 A 的 Windows SSH，采集硬件并判断可行性。保留 Windows，实际版本与安装空间根据现场决定。
能自动完成且已授权的操作请自动完成；清空 U 盘或分区前展示具体目标与备份验证结果。阶段 00 用完整 PowerShell 代码配置 SSH，其他人工步骤优先 GUI，每个阶段说明进度；重启前保存续接记录，遇到问题引导我拍照反馈。进入 macOS 后继续远程检查驱动、双系统启动与功能，不把未实测的项目报告为成功。
```

只发一个链接时，一些 Agent 可能只做网页摘要，因此建议同时附上这段安装请求。普通聊天模型没有终端、SSH 或设备访问能力，读取 Skill 不能凭空获得这些能力。

**给 Agent 的仓库获取规则：** 首先读取入口并理解边界。具备 git 时把用户提供的准确仓库克隆到 B 的新目录，记录来源、分支与完整提交号；已有目录先检查来源与本地变更，不强制覆盖。没有 git 时下载对应提交的源码归档并记录来源。安装过程中固定该快照，不自动切换 main 的新内容。只有网页读取能力时可引导用户操作，但不能声称已自动执行或省略检查。目录中的脚本运行前仍需审阅。

## 包含什么

| 入口 | 用途 |
|---|---|
| [macos-remote-install/SKILL.md](macos-remote-install/SKILL.md) | 跨 Agent 的精简技能入口，按阶段加载资料 |
| [AI-GUIDE.md](AI-GUIDE.md) | 从相同内容合成的单文件指南，适合直接附给 Agent |
| [START-HERE.md](START-HERE.md) | 本地文件夹／WorkBuddy 使用方式 |
| [WorkBuddy 适配包](https://github.com/zxmls-ai/Hackintosh-skill/raw/refs/heads/main/downloads/macos-remote-install-workbuddy-v0.1.3.zip) | 需要本地技能导入时下载；新版流程待实机复测 |
| [references](macos-remote-install/references/) | SSH、兼容性、备份分区、EFI、安装、驱动、排错、续接 |
| [scripts](macos-remote-install/scripts/) | SSH 服务与防火墙配置、只读采集、磁盘身份核对、文件校验、进度记录 |
| [案例参考](macos-remote-install/references/case-14700k-4070ti-super.md) | 14700K＋4070 Ti SUPER 的脱敏经验及未解决问题 |
| [VALIDATION.md](VALIDATION.md) | 本版实际测试范围和未测试部分 |
| [TEST-FEEDBACK.md](TEST-FEEDBACK.md) | 实机测试反馈表 |

阶段：接通 Windows SSH → 采集和兼容性判断 → 备份与空间规划 → EFI 与恢复 U 盘 → 用户协助启动安装 → 接通 macOS SSH → 驱动和功能检查 → 硬盘独立引导与交付。

**开始前：** 默认使用 A 的 Windows 实际账户名与非空账户密码连接，Hello PIN 不能代替密码，不要求先配置公钥。Agent 直接展示 [SKILL 中完整的管理员 PowerShell 代码](macos-remote-install/SKILL.md)，取消 GUI 安装路线。脚本按需安装服务器、设置开机自启、启动服务、核验 TCP 22 的监听进程，并创建或修复持久防火墙规则。规则覆盖所有网络类型，新增放行范围为本地子网；跨网段由 Agent 按实际来源调整。本机检查后仍需由 B 验证 SSH 和 SFTP，详细见 [00 远程接入](macos-remote-install/references/01-remote-access.md)。

**正在测试旧版的用户：** 保留现有任务记录、已安装服务和可用连接。让 Agent 获取 v0.1.3 对应的仓库提交或重新导入新版 WorkBuddy 包，重新读取 SKILL 与远程接入参考，核对现场后续接；不要只刷新网页后假定本地旧 Skill 已更新，也不要为升级指南重装系统。固定并记录新提交号，其余阶段继续按该快照执行。

## 自动化的边界

Agent 可远程采集硬件、检查分区与备份、下载并校验文件、生成针对本机的配置和操作脚本，完成已经授权的修改。需要区分 A/B，写磁盘前核对稳定身份、实际布局和操作范围，不能照抄盘号或盘符。

插拔设备、拍启动画面、没有远程 KVM 时的 BIOS／恢复环境 GUI、Apple 账户登录与实际设备测试，由用户配合。具备权限并获得合适时机授权后，重启本身可自动执行；后续仍要处理 SSH 断线与地址变化。

配套工具不包含一键清盘器。需要的磁盘操作由 Agent 在现场生成可审查的目标专用步骤，完成备份和目标确认后执行。身份工具只校验对象，不代替操作授权或恢复测试。

## 公开内容与运行记录

仓库只包含原创文档、脚本、测试与脱敏案例，不包含 macOS 镜像、驱动二进制、个人 EFI、账户密码或真实机器唯一标识。组件按流程从各自原作者取得并锁定版本。

每次安装的数据保存在 B 的私有 runs 目录。提交 issue 前去掉凭据、IP、主机名、磁盘／SMBIOS 序列号、恢复密钥和截图中的个人信息。不要直接上传整个 runs、EFI 或硬件采集目录。

## 验证与维护

Python 工具使用标准库，要求 Python 3.10+。在仓库根目录运行：

```text
python -m unittest discover -s tests -v
```

这些测试使用合成数据，不连接设备，不分区，不证明真实 macOS 安装成功。WorkBuddy＋DeepSeek 和目标机器的完整实机流程需要另行验收，结果见 [VALIDATION.md](VALIDATION.md)。

Windows SSH 代码以 [enable-windows-ssh.ps1](macos-remote-install/scripts/enable-windows-ssh.ps1) 为源，构建时同步进主入口；工作流正文维护在 [SKILL.md](macos-remote-install/SKILL.md) 和 references。AI-GUIDE 与 WorkBuddy 入口由 [tools/build_release.py](tools/build_release.py) 同步生成。使用反馈和改进方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。

下载包的 SHA256 见 [downloads/SHA256SUMS.txt](https://github.com/zxmls-ai/Hackintosh-skill/blob/main/downloads/SHA256SUMS.txt)。需要完整源码，可用本页 Code → Download ZIP，或让 Agent 克隆仓库并固定提交号。

[MIT 许可证](LICENSE) 仅覆盖本仓库原创内容；链接到的操作系统、工具与驱动保留各自许可。
