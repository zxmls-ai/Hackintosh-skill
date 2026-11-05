# 10 先找现成解，再适配本机

**每次选 EFI 起点、准备修改设备驱动或收到新的引导故障，先在 B 查路线。** 工具目录给出检索起点、需要的输入和预期产物。查证当前版本的适配范围后，再调用生成器或修改测试副本。用[日常交接卡](08-state-and-tools.md)告诉用户当前结果和需要配合的动作。下面的命令和记录由 Agent 完成。

## 选哪条路

**新建安装 EFI 时，先给用户三个选项，再开始制作。** 控制器在 03 返回 `next_action=choose-efi`，按原样展示；用户已在当前对话明确选择时直接登记，不能让用户再选一次。

| 选项 | 向用户说明 | Agent 的下一步 |
|---|---|---|
| **a · RapidEFI-Tool（推荐）** | 先用开源工具生成，再按本机情况调整 | 执行 `choose-efi --choice a`，锁定 RapidEFI 版本，按下方固定流程导出原始 EFI |
| **b · 寻找相似配置** | AI 查找相近机型的成功配置，核对差异后修改 | 执行 `choose-efi --choice b`，登记可复核的案例为 `recipe`，独立处理本机身份、ACPI 与 USB 映射 |
| **c · AI 生成** | AI 按官方模板和真实硬件资料逐项生成，需要更多核对 | 执行 `choose-efi --choice c`，从锁定 OpenCorePkg 的 `Docs/Sample.plist` 建立；来源登记为官方 `recipe` |

这三个选项都要保存原始配置并通过 ACPI、ocvalidate、EFI 审计和介质回读检查。已有同机成功 EFI 一并留作排错对照；未经用户选择，不用它悄悄替换本轮路线。选定路线确实不可用时，说明原因和可选替代路线，再让用户改选。

下面的默认来源优先级用于未指定路线的硬件修复与旧任务。新建 EFI 按 a／b／c 的明确选择执行，不要求选择 b／c 的用户先假称两套生成器都已核查失败。

1. 先查同一台机器、同阶段的成功产物，找出对应的启动或功能实测。比对主板、BIOS、硬件 ID、显示接线、系统 build、架构和用途。若相符，保存原始副本作为基线；若改变，写明差异。
2. 缺少适用基线时查维护者的工具、驱动项目或已落地的上游修复。固定 tag、提交或可识别的发行版本，保存一份有关键支持条件的来源摘录或日志。按准确板型／设备 ID、macOS build、架构与症状查发布说明、设备匹配表、issue、关联 PR 和 CI 产物。核对某项修复是否已进入**准备使用的那个二进制**。工具网页和包下载失败时按 [下载与中转](04-installer.md) 处理。
3. 适合的工具均无法解决时，才依据对应版本的官方模板、维护者的具体解决步骤，在独立副本中做一项可验证的修改。社区 EFI 与论坛案例仅用于寻找有出处的差异；对其他机器的序列号、USB 映射、DSDT 和身份数据分别处理。找不到有依据的做法时交接此问题，继续可做的设备检查。

| 问题 | 首查的实际入口 | Agent 要取回的东西 |
|---|---|---|
| 新建安装 EFI | [RapidEFI](https://github.com/JeoJay127/RapidEFI-Tool) 的自动配置或 [OpCore Simplify](https://github.com/lzhoang2801/OpCore-Simplify) 的硬件报告工作流 | A 的报告、原始 ACPI、生成器版本、未修改的 EFI 及配置。RapidEFI 如导出 configModel 一并保留。 |
| ACPI、USB | [SSDTTime](https://github.com/corpnewt/SSDTTime)、[USBToolBox](https://github.com/USBToolBox/tool) | 从 A 原始表生成的 AML 和配套重命名、实际插孔的发现记录及映射。分别核对作用域、匹配和启用状态。 |
| GPU、有线、无线或音频 | 用下方 lookup 按问题找原项目，再按设备 ID 深查。工具目录可补充其他已维护分支及作者给出的具体修复。 | 锁定的驱动、依赖、证据、回退包；最终包与实际加载位置都要核对。 |

### RapidEFI 的固定操作与自动化

在 **A 的可见 Windows 桌面**运行时，固定顺序是 **打开 RapidEFI → 配置 EFI／自动配置 EFI → 刷新硬件信息并等待完成 → 在 EFI 设置中确认目标 macOS 版本 → 输出 EFI并等待成功**。先读回主板、处理器和目标版本再导出。页面加载、扫描完成和生成成功分别检查，不按固定延时盲点。

有桌面操作工具时，让 Agent 完成这组点击。可使用按钮／控件定位，或截图识别后点击并读回页面。A 有已授权的 RDP／远程桌面会话时，可以从 B 的桌面工具操作该会话；记录实际使用的交互会话。单独 SSH 启动的进程可能不在用户可见桌面，不能把进程存在算成可控窗口，也不要在隐藏会话连续试坐标。

也可以在 **B** 运行 RapidEFI：先从 A 取得该工具支持的硬件报告与原始 ACPI，然后在 B 的自动配置页**导入 A 的硬件资料**，确认界面显示的是 A，再选目标版本并输出。此模式禁止点“刷新硬件信息”把资料替换成 B 的硬件。B 生成的 EFI 在 B 的桌面取回；A 生成的 EFI在 A 的桌面取回，再由 SFTP 传回 B。

截至本版核对，官方 [启动入口](https://github.com/JeoJay127/RapidEFI-Tool/blob/main/lib/main.dart) 没有暴露受支持的批量生成参数。优先自动操作现有 GUI，不虚构 `--auto`／`--output` 等命令行接口。其他 Agent 没有桌面操作能力时，一次给用户上述固定动作，请其完成导出；不因此擅自改选 b 或 c。进入桌面、授权远程会话等必要人类动作单独说明，后续点击合并完成。

### 从实际桌面取回产物

RapidEFI Windows 默认输出到**运行它的用户桌面**，不是固定的 C 盘根目录、程序目录或 `C:\EFI`。当前 [输出路径实现](https://github.com/JeoJay127/RapidEFI-Tool/blob/main/lib/utils/file_util.dart) 使用 `%USERPROFILE%\Desktop`；还要核对实际生成成功提示、用户选择的输出目录及 Windows 重定向桌面。不能把 B 的桌面当 A 的桌面，也不能把 SSH 账户桌面当成另一个实际运行账户的桌面。

Agent 在运行 RapidEFI 的 Windows 主机和账户上记录生成开始时间，导出后先按成功提示路径读取。需要发现候选目录时运行包内只读助手；`-StartedAfter` 填这次实际开始时间，`-DesktopPath` 可填已确认的实际输出桌面。示例中的时间由 Agent 替换。

```powershell
& .\scripts\find-rapidefi-output.ps1 -StartedAfter '<本次开始时间，带时区>'
# 若由其他用户运行或选择了其他桌面／输出目录，显式传入实际路径。
& .\scripts\find-rapidefi-output.ps1 -DesktopPath '<实际运行用户的桌面或输出目录>' -StartedAfter '<本次开始时间，带时区>'
```

助手返回候选 EFI、config 哈希、时间及同级 configModel；多个候选或无本次新增证据时，再和成功提示核对，不能直接取最近的旧目录。完整保留 `EFI/OC/config.plist`、`EFI/BOOT/BOOTx64.efi`、ACPI、Kexts、Drivers，以及实际存在的 configModel。归档生成器的原始输出后，再复制到本轮测试目录调整。同版本 ocvalidate 与真实 A 的适配审核通过，才进入写盘。

**在网站找同型成功案例。** 搜“主板完整型号＋修订号＋BIOS＋macOS build＋症状／设备 ID”。优先有启动或功能实测、原始配置和修复提交的案例。取回它相对上游究竟改了哪几个字段或组件，并核对本机命名空间和硬件路径。符合条件时把这份可复现步骤登记为 recipe，再从自己的生成器输出上应用最小差异。若用户明确在测试“从零生成”的能力，旧成功 EFI 可作为独立对照，把本轮为何不直接复用写入记录。

## 一次查询与登记

在技能目录运行，尖括号由 Agent 替换。lookup 开始时离线可用。它返回候选项目清单及可填写的 `template`；Agent 自己读取项目、获取适配证据、把填好的模板存入私有 run。运行同一组命令可处理 `efi/acpi/usb/gpu/ethernet/wifi/bluetooth/audio/boot/other`。

```text
python scripts/solutions.py lookup efi --target "<A的板型和安装阶段>"
python scripts/solutions.py lookup ethernet --target "10EC:8127"
python scripts/solutions.py check --run "<run>" --file "evidence/attempt-01/source.json"
python scripts/workflow.py --run "<run>" --json select-source --file "<run>/evidence/attempt-01/source.json"
```

模板的 `target` 用稳定设备 ID，EFI 用固定的板型与用途。`environment` 写明目标 macOS／架构及相关固件条件。`hardware_evidence` 指向本轮原始硬件／故障采集。每个候选有三个状态，`unchecked` 表示待确认，`excluded` 表示已经核查并记录排除依据，`usable` 表示匹配。Agent 对已核查项填 `fit` 和 `evidence`；命中项另填不可随分支移动的 `revision`，如 release tag、完整提交、带哈希的文档或基线快照标识。来源文件与硬件文件使用 run 内的相对路径。新增项目按相同格式提供原作者 HTTPS 来源，内置目录可以扩展。

未指定 EFI 路线的旧任务和硬件修复仍按 `baseline → project → recipe`；EFI 的旧式模板回退需要记录两种已列生成器的核查结果。新任务先 `choose-efi --choice a|b|c`，预查来源时 `solutions.py check` 同时传 `--efi-route a|b|c`，控制器会按已登记的选择核对来源。选 b 使用实际案例 recipe，选 c 使用 OpenCorePkg 官方模板 recipe，不能登记成 RapidEFI 生成。工具检查顺序和文件字节，来源适配及实际结果仍须核验。没有适用来源时保留记录并交接，不用改版本号或改写报告充当新证据。

## 原始产物和阶段报告

- **03-media** 选定来源后再构建。先在选中行填好 `base_config`，指向原始基线、生成器实际导出的或官方 Sample 的 plist 在 run 中的预定位置。保留它的原始字节，在新目录复制并适配。用 [EFI 比较](09-efi-diagnostics.md) 记录原始配置到本机候选的差异，按硬件依据只改必要内容。同版本 ocvalidate、原始 ACPI 审核、写后回读及原有确认照常执行。在已有 review JSON 顶层加 `"source_plan": "evidence/attempt-01/source.json"`。没有来源登记或没有合格的原始 plist 时，控制器拦住 03 验收。
- **03、04、06 的故障修改** 先按当前阶段登记来源，再在既有 diagnose JSON 顶层填 `source_plan`，其 `target` 与来源记录一致。保留不变的基线、最小差异、可观察的预期和可执行的回退。每项设备各自跟踪。
- **06-devices** 用户新报告只需描述实测。Agent 在 review 顶层填 `source_plans` 数组，列出本阶段实施修复及回滚所用的各项记录。若全阶段只盘点和测试，给空数组并用 `no_driver_changes` 写明情况。没有效果、需要插拔或等待授权的设备保留待办，先做下一件，沿用日常交接卡。

## 两次没有进展后

受控诊断记录同一问题类别、目标、来源、版本及本轮硬件证据下已实施或回滚的试验。两轮后再次提交该组合的 diagnose，将返回 `SOLUTION_RETRY_LIMIT`。先核对实际启动或加载的是哪份文件，再取得新的现场证据或回到有独立依据的基线。未实施的方案不计次数。控制器的限制适用于经它登记的操作，无法阻止其他工具在外部直接写盘。

新来源也没有推进时，停止这个设备的自动修改。在私有目录交接一页，列出 **硬件与 build、当前可启动基线、查过的来源及版本、两轮改动与实际结果、已排除的做法、恢复入口、下一条最能区分原因的证据**。可将该记录交给更有经验的 Agent 或维护者，由用户决定是否对外分享。其他设备继续，阶段状态如实保留“部分可用／待验证”。

命中上限时，控制器的 JSON 输出在 `details.handoff` 给出所选来源、证据路径，以及最近两次计划、结果与观察文件的路径和哈希。把这份私有索引连同现有 run 交给下一个 Agent，原试验可以直接追溯。
