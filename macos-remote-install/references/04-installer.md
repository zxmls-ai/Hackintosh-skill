# 04 下载、组装 EFI 与制作安装介质

## 锁定版本与来源

下载、EFI 组装、文件校验和已经授权的写盘连续执行，用户无需每下载一个组件回复“继续”。仅在需要插 U 盘、确认具体清空目标或准备重启时交接；默认三项短输出，详细版本与哈希留在日志。

按硬件报告选择 macOS 和 OC 组合。在任务目录记录每项 URL、标签／提交、下载时间、SHA256、用途、适配范围和校验证据。优先官方稳定发布；实验构建注明原因。镜像站只解决传输问题，不能替代原作者来源核对。不把“最新”作为固定版本号，也不擅自升级安装中已锁定的组件。

OpenCore 程序、OpenRuntime、Sample.plist、Configuration 文档和 ocvalidate 来自**同一个发布包**。恢复镜像从 Apple 服务获取，可使用该 OC 包中的 macrecovery；先看当前 `--help` 与文档再选 board-id／参数。不要凭记忆复制“latest”等于 Sequoia 的老命令。下载后验证实际镜像版本与对应 chunklist；镜像版本和最终联网安装的完整系统版本分别记录。[Windows 制作介质](https://dortania.github.io/OpenCore-Install-Guide/installer-guide/windows-install.html)

恢复镜像是安装恢复环境，不是完整离线系统镜像，也不是 BIOS 固件。恢复环境联网必须可用，否则先准备可用网卡／驱动或明确的离线安装方案。若用户指定精确小版本但 Apple 恢复服务器不提供，说明实际可取得版本，不静默替换。

## ACPI：默认不增加重启

固定优先级：复用本任务已验证的 A 原始表 → 在 A 的 Windows 中自动准备 Python 并采集 → 默认路线经诊断仍失败时让用户选择备用路线。不能把“A 没有 Python”直接改成“先重启采集”，也不能为追求不安装工具而增加人工操作。已有原作者原生导出工具且能验证输出时，可直接使用，仍然不用 Python 或重启。

| 路线 | Agent 做什么 | 用户做什么 |
|---|---|---|
| 默认：Windows + Python | 复用兼容解释器；缺少时安装官方用户级 Python，准备锁定的 SSDTTime／ACPICA，在 A 导出后传回 B | 通常无需操作；在首次短提示中说明可选免 Python 路线，不另开一轮安装确认 |
| 可选：免 Python 的 SysReport | 准备同版本 OpenCore DEBUG 诊断配置，开启 SysReport，取回真实表后再制作安装配置 | 用户选择后，额外启动到 OC 菜单并回 Windows；采集时不进入 macOS 恢复 |

默认路线的连续动作：

1. 用当前已验证的 SSH 连接确认 A 身份；在 A 实际执行 Python 版本／标准库检查，不能把商店别名当成解释器。已存在兼容版本不重复安装。
2. 缺少时由 Agent 从 Python 官方渠道获取与所选工具兼容的 Windows 安装包，锁定版本和下载证据，校验签名／发布方提供的校验值。默认用户级安装，使用完整解释器路径；不要改系统 PATH、文件关联或覆盖现有 Python。传统 EXE 安装器可使用其实际支持的 `/quiet`、`InstallAllUsers=0`、`PrependPath=0`、`Include_launcher=0`、`Include_test=0` 和独立 `TargetDir`；先核对该安装器帮助，安装后真实运行验证。不能把安装器参数直接用于 MSIX／安装管理器。[Python Windows 安装说明](https://docs.python.org/3/using/windows.html)
3. 锁定原作者 SSDTTime 提交及其实际依赖，工具放进任务目录。通过 SSH 调用解释器完整路径与 `SSDTTime.py`；不要假设 `.bat` 的交互式自动下载器适合无人值守，也不要编造工具没有的 CLI。需要交互时根据锁定版本的实际菜单／源代码传入输入；使用库调用也先核对实际接口。SSDTTime 的 Windows 导出会使用 ACPICA 工具，Python 本身不是唯一能够读取 ACPI 的途径。[SSDTTime](https://github.com/corpnewt/SSDTTime)、[Windows 导出实现](https://github.com/corpnewt/SSDTTime/blob/master/Scripts/dsdt.py)
4. 必须在 **A** 导出，B 负责下载、分析和保存；在 B 执行导出得到的是 B 的表。保存 A 身份、BIOS 版本、工具版本、退出码、时间及原始输出。取回 DSDT 和可取得的 SSDT 原始二进制，保留未修改副本；检查实际签名、长度、校验和及哈希，并用锁定的 iasl 分析／反编译。缺表、无法解析或依赖不全时停止安装交接，处理具体原因，不以“命令已运行”算完成。
5. 按本机命名空间和硬件生成／选取确有必要的补丁，记录每个启用补丁的原始表依据与用途。不是所有机器都需要相同 SSDT，也不要把整份别机 DSDT 注入。ACPI 表完整仍不能证明 Booter／UEFI／CPU 配置正确：单独审核实际 config、固件内存映射依据与适用的 CPU 设置。

遇到权限、依赖、下载／证书或导出错误，保留日志，在 Windows 中做针对性恢复；不关闭 TLS 校验、不循环盲试、不擅自切换重启路线。用户明确不装 Python或默认路线无法完成时，用一句话给出 SysReport 的操作代价，让用户选择。用户已经选择则直接执行，不重复确认。

SysReport 路线是**采集启动**：使用所选 OC 版本文档要求的 DEBUG 构建，核对 `Misc → Debug → SysReport`、可写输出位置和日志，设置显示启动菜单并关闭自动倒计时（`ShowPicker=true`、`Timeout=0`，以该版本文档为准）。交接明确“停在 OC 菜单，不选 macOS；随后从主板 Windows Boot Manager 回 Windows”。确认导出文件实际存在并有效后，再组装安装 EFI；仅开启选项或看到菜单不能算采集成功。保留 Windows 引导和 U 盘备份，不覆盖硬盘 ESP 来采集。[OpenCore 配置文档](https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/Configuration.tex)

## 03 的程序验收清单

`review` 的 `acpi_tables` 检查必须为 `pass`，并增加 `manifest` 字段，值为任务目录内的相对路径，例如 `inventory/acpi/collection.json`。该清单采用下面的结构；所有 SHA256、UUID、路径和分析均由实际采集生成，不能把示例当证据。

```json
{
  "schema": "acpi-evidence-v1",
  "machine_uuid": "实际 A 的 UUID，与当前任务相符",
  "method": "windows-python",
  "capture_log": {"path": "evidence/acpi-capture.txt", "sha256": "实际 SHA256"},
  "tables": [{"path": "inventory/acpi/DSDT.aml", "sha256": "实际 SHA256"}],
  "config": {"path": "staging/EFI/OC/config.plist", "sha256": "实际 SHA256"},
  "assessment": {"path": "evidence/acpi-assessment.md", "sha256": "实际 SHA256"},
  "patches": [{
    "path": "staging/EFI/OC/ACPI/SSDT-EXAMPLE.aml",
    "sha256": "实际 SHA256",
    "based_on": ["inventory/acpi/DSDT.aml"],
    "reason": "实际本机设备路径、补丁用途及依据"
  }]
}
```

`tables` 列出实际 DSDT／SSDT 原始文件，至少有 DSDT；其他原始表同样保留，但不塞进这个专用于 AML 表的列表。`patches` 必须与当前 config 中全部启用的 `ACPI → Add` 文件一致，并关联实际原始表。经分析确实不需要 Add 时可为空，但须提供 `no_add_reason` 与完整分析；不能为了越过检查编造“无需补丁”。`method` 另可取 `windows-native` 或 `opencore-sysreport`；后者还要有 `user_choice` 文件路径与 SHA256，记录用户选择。`firmware_config_review` 单独引用固件／Booter／CPU 判断证据。

控制器检查实际文件内容、哈希、表头／长度／校验和、目标字段、当前配置和启用补丁的一致性。清单及文件纳入后续完整性检查；修改 EFI 后必须重新评估并生成匹配清单。程序不判断任意分析文字是否真实，也无法替代 A 端采集来源的核对或实际启动测试。全部要求仍受阶段合同和真实授权约束。

阶段 03 未通过时，下载、备份以及已授权的 U 盘准备可继续，但不能提示“选择 macOS 恢复环境开始安装”。`ocvalidate` 通过不等于 ACPI、固件或启动已验证。控制器只能阻止其自身阶段推进，Agent 不得绕过它直接安排安装启动。

首次试启动还必须有可取回的诊断日志：默认 `Misc → Debug → Target=67`（启用日志、屏幕与文件）和 `AppleDebug=true`，核对 U 盘可写、空余空间、构建与文件位置，重启回来读取实际日志。控制器检查 Target 的日志启用／文件位和 AppleDebug；`Target=3` 只有屏幕输出，会被 `EFI_DIAGNOSTICS_INVALID` 拒绝。这只是启动前配置检查，不保证固件一定写出日志；没有日志时处理写入原因，不把缺失当成功。SysReport 仍须 DEBUG 构建；REL 加开启选项不生效。初次排障默认使用同版本 DEBUG，稳定后再评估关闭诊断。选项语义以该 OC 版本官方文档为准。

## EFI 组装

从目标版本 Sample.plist 和 X64 目录开始，按硬件分支建立自己的 EFI。RapidEFI、OC 配置器或其他自动工具可以辅助，但生成结果必须审查和校验，不能取代硬件判断。只有 UI 的工具不能假设存在 CLI；SSH 启动看不见的 GUI 不算生成成功。

按需要加入文件：必要 ACPI、VirtualSMC、Lilu 及实际需要的插件、网络驱动、USB 映射等；遵循依赖顺序。不要为了“通用”加载所有网卡、全部显卡补丁和大量来源不明 SSDT。具体设置以原作者相应系统版本说明为准，未知参数先查证。

SMBIOS 选择与身份生成按本机路线完成。保留 Windows 时，BIOS 的 Secure Boot 与 OC 的 SecureBootModel 是两种设置；不能互相混淆。显卡驱动要求改变 SIP／AMFI 等安全设置时，逐项说明并按该驱动当前文档操作，不能把案例中的关闭参数作为默认值。

需要先进入桌面再安装 GPU 驱动的方案，维护独立阶段：

1. `install`：用于恢复／首次安装的最小可启动配置。
2. `prepare-driver`：确有必要时应用驱动安装前提，重启验证。
3. `runtime`：驱动已安装并验证后启用的完整配置。

三者保存清晰文件清单与差异。禁止把运行期强依赖尚未安装驱动的配置提前放进首次启动介质。

## 校验

在 B 可运行 `python scripts/agentkit.py check-efi --root <EFI目录>` 做引用与路径检查，随后运行**同版本** ocvalidate。配套检查工具不是 ocvalidate 替代品，也不能证明能启动。核对启用的 ACPI、驱动、kext、Info.plist 与执行文件均存在；无版本冲突或重复注入；禁用项缺文件不应误报为启动失败。

核对 ACPI 补丁是否匹配当前表、USB 地图是否对应本机、CPU 核心补丁是否对应实际硬件。任何例外要有依据并记录。ocvalidate 不检查真实硬件兼容性，也不保证补丁有效。

## U 盘目录与复制

在已确认的 FAT32 安装分区根目录，常规 X64 恢复介质布局为：

```text
EFI/
  BOOT/BOOTx64.efi
  OC/OpenCore.efi
  OC/config.plist
  OC/ACPI/...
  OC/Drivers/...
  OC/Kexts/...
com.apple.recovery.boot/
  BaseSystem.dmg + BaseSystem.chunklist
  或 RecoveryImage.dmg + RecoveryImage.chunklist
```

文件名称与配对应来自实际下载结果，不把两套文件混合。避免 EFI/EFI/OC 的多嵌套错误。若采用别的安装介质路线，说明差异并按该路线验证。

传输用 SFTP／可靠复制；网络中断后先确认部分文件，不能把“上传开始”当作完成。写入后从 A 上的 U 盘回读哈希，与 staging 比对；检查实际文件系统与空间，保存最终清单。准备日志输出和可回到 Windows 的启动办法，之后再进入 BIOS 交接。
