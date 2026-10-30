# Hackintosh-skill

将这份指南交给 Codex、Claude Code、DeepSeek Harness、WorkBuddy 等 Agent，按统一流程协助安装和排错，尽量减少重复操作与无依据试错。

> **测试阶段声明／免责声明**
>
> 本 Skill 仍在开发与实机测试中，可能存在遗漏、错误和未覆盖的硬件情况，**不保证流程无误、安装成功或所有功能正常**，也不是适用于所有电脑的通用 EFI。
>
> **不同 Agent 工具、大模型、版本、上下文与工具权限的能力不同，即使读取同一份 Skill，也可能出现执行顺序、理解和排错结果的差异。** 标准流程与检查工具只能减少不确定性，不能消除 AI 误判或保证每一步均被正确执行。
>
> 分区、格式化、修改引导及安装驱动可能导致数据丢失或系统无法启动。请先备份重要数据并确认可恢复；涉及写盘时核对目标，保留 Windows 与可用引导的回退方式。本项目按 MIT 许可证“按现状”提供，不作明示或默示担保；请勿将尚未验证的配置直接用于唯一的工作环境。

让运行在 **B 电脑**上的 Agent，通过远程连接协助 **A 电脑**安装、调试与验收 macOS，保留 Windows。面向小白，把能够自动完成的工作交给 Agent，Windows SSH 用一次粘贴的管理员 PowerShell 配置，其余现场操作优先 GUI。

**v0.2.5：根据实机排错补充固定的 EFI 来源选择、有效配置审计与对照试验流程；新增只读 EFI 比较工具，防止把文件存在、校验通过或批量试验误报为根因。** 00 程序验收，01～08 合同审核；异常处理后回到原步骤。实际执行主路线为 x86-64 UEFI PC；不支持的硬件应报告限制，不承诺通过修改参数解决。

## 给 Agent 一个仓库链接

在 WorkBuddy＋DeepSeek 或具备文件、终端与联网能力的其他 Agent 中，直接发送下面这段话：

```text
仓库：https://github.com/zxmls-ai/Hackintosh-skill

请先读取仓库 README.md，再读取 macos-remote-install/SKILL.md，按它协助我在另一台 A 电脑安装 OpenCore 与 macOS。你运行在 B 电脑。先读取 references/00-controller.md，在 B 调用 workflow.py 初始化或续接任务，按 next_action 执行并原样展示 display；00 不另写连接器或手改状态，之后按阶段合同采集硬件并判断可行性。保留 Windows，实际版本与安装空间根据现场决定。
能自动完成且已授权的操作请自动完成；清空 U 盘或分区前展示具体目标与备份验证结果。阶段 00 用完整 PowerShell 代码配置 SSH，其他人工步骤优先 GUI，每阶段只简短说明“进度／下一步／需要你”；合并能一次完成的操作，详细日志自行保存；重启前保存续接记录，遇到问题引导我拍照反馈。进入 macOS 后继续远程检查驱动、双系统启动与功能，不把未实测的项目报告为成功。
```

只发一个链接时，一些 Agent 可能只做网页摘要，因此建议同时附上这段安装请求。普通聊天模型没有终端、SSH 或设备访问能力，读取 Skill 不能凭空获得这些能力。

**给 Agent 的仓库获取规则：** 首先读取入口并理解边界。具备 git 时把用户提供的准确仓库克隆到 B 的新目录，记录来源、分支与完整提交号；已有目录先检查来源与本地变更，不强制覆盖。没有 git 时下载对应提交的源码归档并记录来源。安装过程中固定该快照，不自动切换 main 的新内容。只有网页读取能力时可引导用户操作，但不能声称已自动执行或省略检查。目录中的脚本运行前仍需审阅。

## 包含什么

| 入口 | 用途 |
|---|---|
| [macos-remote-install/SKILL.md](macos-remote-install/SKILL.md) | 跨 Agent 的精简技能入口，按阶段加载资料 |
| [AI-GUIDE.md](AI-GUIDE.md) | 从相同内容合成的单文件指南，适合直接附给 Agent |
| [START-HERE.md](START-HERE.md) | 本地文件夹／WorkBuddy 使用方式 |
| [WorkBuddy 适配包](https://github.com/zxmls-ai/Hackintosh-skill/raw/refs/heads/main/downloads/macos-remote-install-workbuddy-v0.2.5.zip) | 需要本地技能导入时下载；SSH 修复已有单机实测，跨 Agent 流程继续验证 |
| [references](macos-remote-install/references/) | SSH、兼容性、备份分区、EFI、安装、驱动、排错、续接 |
| [流程规范与调用方式](macos-remote-install/references/00-controller.md) | 固定输入输出、错误恢复、断点续接与合同审核 |
| [EFI 决策与排错](macos-remote-install/references/09-efi-diagnostics.md) | 起点选择、有效配置审计、基线比较与有限试验，避免无依据堆补丁 |
| [阶段合同](macos-remote-install/workflow.json) | 00～08 的顺序、输入、动作、验收和恢复位置 |
| [scripts](macos-remote-install/scripts/) | 流程控制器、固定 SSH 连接器、采集、磁盘身份与文件校验 |
| [案例参考](macos-remote-install/references/case-14700k-4070ti-super.md) | 14700K＋4070 Ti SUPER 的脱敏经验及未解决问题 |
| [VALIDATION.md](VALIDATION.md) | 本版实际测试范围和未测试部分 |
| [TEST-FEEDBACK.md](TEST-FEEDBACK.md) | 实机测试反馈表 |

阶段：接通 Windows SSH → 采集和兼容性判断 → 备份与空间规划 → EFI 与恢复 U 盘 → 用户协助启动安装 → 接通 macOS SSH → 驱动和功能检查 → 硬盘独立引导与交付。

**开始前：** 默认使用 A 的 Windows 实际账户名与非空账户密码连接，Hello PIN 不能代替密码，不要求先配置公钥。Agent 先运行 [流程控制器](macos-remote-install/references/00-controller.md)，从返回文件读取完整管理员 PowerShell 代码交给用户，取消 GUI 安装路线。脚本按需安装服务器、设置开机自启、启动服务、核验 TCP 22 的监听进程，并创建或修复持久防火墙规则。规则覆盖所有网络类型，新增放行范围为本地子网；跨网段由 Agent 按实际来源调整。安装、校验、IP／用户名、主机指纹与网段比较合并输出一个连接结果。复制结果块到 B，将第一行占位替换为账户密码或 B 上的密码文件完整路径，与连接信息一起发送；已提供可填“已提供”。目标 macOS 版本尚未知时一并补充（未定也可以）；B 自动核验握手、SSH、SFTP 并采集硬件。网段相同不等于可达，详细见 [00 远程接入](macos-remote-install/references/01-remote-access.md)。

**正在测试旧版的用户：** 保留现有任务记录、已安装服务和可用连接。让 Agent 获取 v0.2.5 对应的仓库提交或重新导入新版 WorkBuddy 包，重新读取 SKILL 与远程接入参考，v0.1 任务仍在 00 时用 init 接管；v0.2.0～v0.2.3 受控任务由新版的 upgrade 核对并迁移，再 status 续接。升级只接受登记过的源码字节／LF／CRLF 哈希、00～04 的任务，并保留备份、身份与证据；≤0.2.2 旧任务已进 04 时回到 03 补验 ACPI；0.2.3 已通过的阶段保持原位，旧完成记录留作历史，不重做分区或清空 U 盘。程序锁定源文件，后续升级须明确迁移，不能直接覆盖正在运行的快照；不要只刷新网页后假定本地旧 Skill 已更新，也不要为升级指南重装系统。固定并记录新提交号，其余阶段继续按该快照执行。

## 自动化的边界

本版完整执行器覆盖阶段 00。01～08 已有合同和顺序检查，具体工作仍由 Agent 执行及审核；文件或报告存在不等于程序证明硬件可用。固定流程可以减少模型差异，不能让缺少工具的模型获得执行能力，也不能保证任意模型不会绕过规则。

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
