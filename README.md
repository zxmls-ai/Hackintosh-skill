# Hackintosh-skill · v0.2.13

<!-- yarkr:badges:start -->
[![Indexed on Yarkr](https://api.yarkr.com/functions/v1/api/api/v1/badges/repos/zxmls-ai/Hackintosh-skill/version.svg)](https://yarkr.com/arks/zxmls-ai/hackintosh-skill)
<!-- yarkr:badges:end -->

本版优先使用 1401 自动构建 EFI，RapidEFI 作为备用；安装前说明哪些功能需要装完系统后继续修复。仍处测试阶段，详见下方测试声明与验证范围。

你可以在一台电脑上和 AI 助手聊天，让它帮你在另一台 Windows 电脑上检查硬件、准备安装 U 盘，再安装 macOS。默认保留 Windows。

> **测试阶段声明／免责声明**
>
> 本 Skill 仍在开发与实机测试中，可能存在遗漏、错误和未覆盖的硬件情况，**不保证流程无误、安装成功或所有功能正常**，也不是适用于所有电脑的通用 EFI。
>
> **不同 Agent 工具、大模型、版本、上下文与工具权限的能力不同，即使读取同一份 Skill，也可能出现执行顺序、理解和排错结果的差异。** 标准流程与检查工具只能减少不确定性，不能消除 AI 误判或保证每一步均被正确执行。
>
> 分区、格式化、修改引导及安装驱动可能导致数据丢失或系统无法启动。请先备份重要数据并确认可恢复；涉及写盘时核对目标，保留 Windows 与可用引导的回退方式。本项目按 MIT 许可证“按现状”提供，不作明示或默示担保；请勿将尚未验证的配置直接用于唯一的工作环境。

本版新增 [Intel Xe-LP 配置与验证路线](macos-remote-install/references/14-xe-lp.md)，回应 [社区反馈 #1](https://github.com/zxmls-ai/Hackintosh-skill/issues/1)：按真实设备 ID 查 WhateverXe＋Graphics，区分安装前准备和装完后的驱动修复，并检查与 WhateverGreen 的冲突。社区案例不等于所有 Xe 机器均兼容；1401 仍为首选 EFI 生成器。

## 开始前，先分清两台电脑

- **A 电脑是安装机。** 现在运行 Windows，以后要从 U 盘启动，在它的屏幕上安装 macOS。
- **B 电脑是助手机。** 你在这里打开 WorkBuddy 等 AI 工具、看提示、发回复。安装时，B 也会帮你保存进度，方便 A 重启后接着做。

**为什么先连两台电脑？** 聊天里的助手只能操作自己所在的 B。开启远程连接（SSH）后，它才能通过家里的网络读取 A 的硬件、传送安装文件。等 A 重启进入安装画面，你再按它给的清单操作。

**现在准备**　A 可以是 Intel 或 AMD 的 64 位 PC。让 A 进入 Windows，确认账户有管理员权限和非空登录密码。平常用 PIN 解锁的话，也需要知道这个账户的密码。让两台电脑接入同一个路由器下可互访的网络，在 B 打开能读文件、运行命令和联网的 AI 助手。具体硬件由助手检查，你无需自己认型号。

**稍后准备**　一只可以清空的 U 盘、一处能存重要文件备份的位置，以及在 A 前看屏幕、用键鼠、重启选启动项的条件。U 盘和安装空间要多大，助手会根据检查结果告诉你。现在可以先把 U 盘放在手边。

**安装大致分四段**

| 到了哪一步 | 你会看到什么 |
|---|---|
| 00～01　连接和检查 | 助手连上 A 的 Windows，检查能装哪个 macOS、哪些硬件可能需要额外处理。 |
| 02～03　准备安装 | 你确认备份和目标分区，再插入指定 U 盘。助手核对目标、制作启动盘。 |
| 04　现场安装 | 你在 A 从 U 盘启动，按一份清单选择预留分区、安装并完成桌面初始化。 |
| 05～08　装好之后 | 助手重新连接 A，逐项测试硬件，验证拔掉 U 盘后的启动，再交付备份和恢复方法。 |

## 在 B 上开始

在 B 打开 WorkBuddy 或其他能读文件、运行命令的 AI 助手，复制下面两行到对话框即可。

```text
请读取 https://github.com/zxmls-ai/Hackintosh-skill 的 README 和 macos-remote-install/SKILL.md，带我在另一台电脑安装 macOS，并保留 Windows。
我第一次操作。先告诉我两台电脑各做什么、现在要准备什么，再告诉我到哪台电脑做哪一步。清空任何设备前请先和我核对。
```

第一轮会先介绍两台电脑的分工，再给一段完整命令。你在 A 粘贴运行一次，把结果发回 B。助手核对连接后，就可以自动检查硬件。已有受控任务会按保存的进度继续。

想先看看助手会怎么说，可以打开[新手对话预览](新手对话预览.md)。习惯用 WorkBuddy 技能导入的用户，可以直接[下载 v0.2.13 适配包](https://github.com/zxmls-ai/Hackintosh-skill/raw/refs/heads/main/downloads/macos-remote-install-workbuddy-v0.2.13.zip)。遇到仓库访问问题时，见[新手起步](START-HERE.md)。

## 给 Agent 的入口说明

在 B 取得仓库快照并记录分支和完整提交号。已有目录先检查来源与本地变更。没有 git 就取得对应提交的源码归档。用户提供完整离线包时，记录包版本和 SHA256。安装期间固定同一份源码。运行前审阅脚本。只有网页读取权限时进入人工指导模式并说明当前能力。

执行路线面向支持 UEFI 启动的 x86-64 PC。阶段 03 会先让你选择 **1 · 1401（首选推荐）／2 · RapidEFI-Tool（备用）／3 · 相似配置／4 · AI 自行配置（前三种均不可用时）**，再制作 EFI。1401 下载失败先排查网络并寻找可核验的镜像／加速，仍不可用再请你选备用路线。EFI 做好后会提示需要装完 macOS 再修的功能，并带入硬件检查清单。1401 提供免点击 CLI，详见 [1401 路线](macos-remote-install/references/12-1401.md)。有桌面控制能力时由助手自动操作 RapidEFI，按实际桌面或成功提示路径取回产物。安装 EFI 默认展开恢复等辅助项；若开机只有 Windows，可按空格展开隐藏项。阶段 00 由控制器在 B 验证连接，01～08 按阶段要求和现场证据审核。[流程控制器](macos-remote-install/references/00-controller.md)

## 包含什么

| 入口 | 用途 |
|---|---|
| [macos-remote-install/SKILL.md](macos-remote-install/SKILL.md) | 跨 Agent 的精简技能入口，按阶段加载资料 |
| [AI-GUIDE.md](AI-GUIDE.md) | 从相同内容合成的单文件指南，适合直接附给 Agent |
| [START-HERE.md](START-HERE.md) | 第一次启动、离线读取及 WorkBuddy 使用方式 |
| [WorkBuddy 适配包](downloads/) | 本地构建的 ZIP，供支持本地技能导入的 WorkBuddy 客户端使用 |
| [references](macos-remote-install/references/) | SSH、兼容性、备份分区、EFI、安装、驱动、排错、续接 |
| [流程规范与调用方式](macos-remote-install/references/00-controller.md) | 固定输入输出、错误恢复、断点续接与合同审核 |
| [恢复界面安装步骤](macos-remote-install/references/05-boot-handoff.md) | Agent 填好目标后交付：抹掉、安装、重启选择、初始化 |
| [安装后设备验收](macos-remote-install/references/06-postinstall.md) | Metal 计算回读、双网卡、Wi-Fi／蓝牙和下一项操作 |
| [安装前的功能说明](macos-remote-install/references/13-install-expectations.md) | 区分安装必需能力与后置驱动，避免遗漏后续修复 |
| [1401 免点击生成](macos-remote-install/references/12-1401.md) | Windows 命令行采集、规划、构建与独立校验 |
| [安装后固定合同](macos-remote-install/references/11-postinstall-contract.md) | 全机问题清单、修复顺序、阶段门槛与硬盘固件启动项 |
| [现成方案优先手册](macos-remote-install/references/10-existing-solutions.md) | 给 Agent 的查找、选用、审计与交接步骤 |
| [EFI 决策与排错](macos-remote-install/references/09-efi-diagnostics.md) | 起点选择、有效配置审计、基线比较与有限试验，避免无依据堆补丁 |
| [阶段合同](macos-remote-install/workflow.json) | 00～08 的顺序、输入、动作、验收和恢复位置 |
| [scripts](macos-remote-install/scripts/) | 流程控制器、固定 SSH 连接器、采集、磁盘身份与文件校验 |
| [案例参考](macos-remote-install/references/case-14700k-4070ti-super.md) | 14700K＋4070 Ti SUPER 的脱敏经验及未解决问题 |
| [VALIDATION.md](VALIDATION.md) | 本版实际测试范围和未测试部分 |
| [TEST-FEEDBACK.md](TEST-FEEDBACK.md) | 实机测试反馈表 |

**第一次连接。** 在 A 用 Windows 管理员账户登录，在 B 携带 A 输出的两行结果一次回复。第一行按提示填密码或 B 上的密码文件完整路径，第二行保留原样。已有凭据可填“已提供”。想装的 macOS 版本可以顺带写，也可以留待助手检查。详细操作见 [准备工作和远程接入](macos-remote-install/references/01-remote-access.md)。

**已有安装任务可按记录续接。** 保存旧快照和任务记录，在独立目录固定新版本。v0.2.0～v0.2.5 的受控任务可在已登记的 00～04 阶段使用 `upgrade` 后运行 `status`。v0.2.6、v0.2.7 可在 00～06 迁移，正在执行的旧版硬件修复先在旧流程收尾。控制器会核对源文件、状态和历史证据。≤0.2.2 已进入 04 的任务需回 03 补验 ACPI。若历史证据已变化，按控制器的恢复说明处理，并在现场记录中单列实际硬件进度。早期 v0.1 任务仍在 00 时可按入口说明初始化。

## 安装后先修硬件，再移除 U 盘

v0.2.8／v0.2.9 的已登记任务也可 `upgrade`。仍在 05/06 时保留阶段；旧 07/08 回到 06 补验新清单，保留历史和实际磁盘内容，不重复安装。详见[旧任务升级](macos-remote-install/references/11-postinstall-contract.md#旧任务升级)。

进入桌面并接通远程登录后，助手先对照 Windows 清单检查全部硬件与适用系统功能，展示未工作／未测试项目。默认每张网卡和显卡优先，查社区与开源项目、备份后逐项修复；暂时修不好就继续下一项，最后集中交代限制。清单未收尾不能跳到写硬盘 EFI。

硬盘引导同时核对 EFI 文件、真实固件 OpenCore 启动项、默认顺序和菜单显示，再安排第一次拔 U 盘冷启动。仅复制文件、设置 LauncherOption、看到设备名称，都不代表功能或启动已通过。参见 [安装后固定合同](macos-remote-install/references/11-postinstall-contract.md)。

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

需要完整源码，可用仓库首页 **Code → Download ZIP**，或让 Agent 克隆仓库并固定提交号。WorkBuddy 包可用[下载校验值](https://github.com/zxmls-ai/Hackintosh-skill/blob/main/downloads/SHA256SUMS.txt)核对。

[MIT 许可证](LICENSE) 仅覆盖本仓库原创内容；链接到的操作系统、工具与驱动保留各自许可。

<!-- yarkr:install:start -->
## Install with Yarkr

This repo is indexed on [Yarkr](https://yarkr.com/arks/zxmls-ai/hackintosh-skill) as the ark [zxmls-ai/hackintosh-skill](https://yarkr.com/arks/zxmls-ai/hackintosh-skill), so its skills install into Claude Code, Codex, Cursor and other agent harnesses with one command.

### CLI

Install the whole ark, which Yarkr keeps equal to this repo:

```bash
npx yarkr-cli sync zxmls-ai/hackintosh-skill
```

Or add individual skills:

```bash
npx yarkr-cli add skill:zxmls-ai/hackintosh-skill/macos-remote-install
```

No Node.js? `curl -fsSL https://yarkr.com/install.sh | sh` (macOS, Linux) or `irm https://yarkr.com/install.ps1 | iex` (Windows PowerShell) installs `yarkr` as a standalone binary; then type `yarkr` in place of `npx yarkr-cli`.

### MCP

Connect your agent to the ark over MCP:

```bash
npx yarkr-cli mcp add zxmls-ai/hackintosh-skill
```

Or point any MCP client at `https://api.yarkr.com/functions/v1/api/mcp/o/zxmls-ai/hackintosh-skill`.
<!-- yarkr:install:end -->
