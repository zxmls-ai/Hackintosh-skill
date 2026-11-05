# 进入桌面后的固定顺序与证据合同

此页在阶段 05 接通 macOS 后读取，与 [06 功能测试方法](06-postinstall.md) 配合。命令在 B 执行，采集器在 A 执行。这里的 JSON、证据路径和控制器错误码留给 Agent；人类只看简短的进度和问题表。

## 顺序不可跳过

`05 接通 macOS → 06 全机扫描 → 展示问题清单 → 网卡／显卡优先逐项查证与修复 → 全表验收／限制确认 → 07 写硬盘 EFI＋注册固件启动项 → 拔 U 盘冷启动 → 08 交付`

桌面显示正常、能 SSH、已有可启动 U 盘，都不能代替阶段 06。修复期间在可回退的测试 EFI 上工作，不提前把试验配置写到硬盘 ESP。若机器本来就在用硬盘 EFI，先备份并准备可用的外部回退方案，不删除现有引导。

## 一次扫描，先把问题说清楚

1. 运行 `collect-macos.sh` 到新的报告目录，保留时间、命令退出码和错误；失败的采集项不能解释成“没有设备”。读取当前系统 build、PCI／USB、驱动、音频、无线、磁盘、网络及电源状态。
2. 与阶段 01 **原始 Windows JSON**逐件对照。每个物理网口和 GPU 单列，Wi-Fi 与蓝牙分列；包括只在 Windows 出现、被安装 EFI 屏蔽或未加载驱动的设备。记录稳定硬件 ID、当前驱动、是否枚举和实际功能测试结果。若 Windows 采集本来缺项，从此前报告／主板资料补查，不能靠 macOS 当前枚举缩小检查范围。
3. 所有机器覆盖 `network/gpu/wifi/bluetooth/usb/audio/storage/cpu-power/sleep/continuity` 十类，必要时添加 `other`（笔记本电池、触控板、摄像头等）。没有某类硬件、没有用户配合测试 Apple 生态功能时也要写明：前者有依据可记不适用；后者是待测，不能当不适用。按用户用途检查接力、通用剪贴板、视频解码等适用功能，不为测试擅自登录 Apple 账户。
4. 先展示**异常和待测清单**，然后用 `record-devices` 登记完整清单。远程无法证明的功能安排实际工作负载或合并现场测试。清单不是“所有功能已自动扫描通过”的报告。

面向人类的首次输出示例（内容必须替换为本轮实测）：

> **06 · 检查和修复硬件**
>
> **现在**　已连上 macOS，完成第一轮检查。
>
> | 项目 | 当前情况 | 接下来 |
> |---|---|---|
> | 第二个网口 | 未生成网络接口 | 核对屏蔽设置与社区驱动 |
> | 显卡加速 | 驱动未加载 | 查适配版本并准备回退 |
> | USB、睡眠 | 尚未实测 | 修复后集中做插拔与唤醒测试 |
>
> **接下来**　先处理网卡和显卡，再检查其余项目；暂时修不好的一项会记下来，继续下一项。
>
> **请你**　暂时无需操作，保留启动 U 盘。

后续只报完成数量、当前项目及下一项；新问题／待用户操作时再展示相关行，不反复刷全表。

## 固定修复循环

每张网卡 → 显卡 → Wi-Fi／蓝牙 → USB → 音频／存储／CPU 电源 → 睡眠／系统功能 → 其他适用设备。

保持当前 SSH 网口可用；“网卡优先”不表示先卸载正在连接的唯一驱动。对于每项：

1. 以设备 ID＋系统 build／架构查询 [现成方案](10-existing-solutions.md)：同机成功基线、原作者设备表／发布、维护者 issue／开源项目。有了候选再 `select-source`；不能凭旧常识判新设备永久无解。记录查过的 URL、版本、适用条件、当前支持／限制和下载情况。
2. 在授权范围内自动下载、核验、备份、准备并尝试已查证的方案。国内网络下载失败按 A／B 代下、中转规则继续。需要新增高影响改动时说明具体变更；不把普通读取和准备反复交给用户。
3. 单项修改后重连并做**本轮功能测试**。网卡要绑定对应接口实际通信，显卡要验证实际渲染／Metal 工作负载；详见 06。只有型号、显存、驱动加载、IP 或旧案例，不能填 `passed`。
4. 同方案相同证据两轮无进展、无已核实方案、包不可得：保存原因、来源、尝试及回退，置 `deferred`，继续下一项。等待插线／试听／重启置 `waiting-user`，也不阻塞独立检查。
5. 可自动工作的队列为空，再一次性给出现场测试清单和仍受限项。用户明确接受具体限制后填 `accepted-limit`；“先跳过”只表示继续其他项目，不表示验收通过。全部行封口后才能阶段 06 review。不得通过删除第二张网卡、把待测改成不适用或另建空任务绕过。

## 清单数据与命令

每次保存**新文件**，不要改已入账证据。所有路径相对私有任务目录，不含凭据。`device-audit-v1` 必需顶层字段：

| 字段 | 内容 |
|---|---|
| `schema`, `machine_uuid`, `macos_build` | schema 名、本任务 A 的身份、此次系统 build |
| `windows_inventory` | 阶段 01 的原始 `collect-windows.ps1` JSON |
| `macos_inventory`, `coverage_review` | 此轮采集索引和逐件覆盖对照文件；记录采集失败的处理 |
| `presented` | 已向用户展示问题清单的交接记录（不是尚未发送的草稿） |
| `rollback` | 当前可用 EFI、系统卷驱动的卸载／回退方式与备用连接记录 |
| `tested_config`, `tested_efi_manifest` | 此轮验收所用 EFI 配置、全 EFI 文件哈希清单 |
| `items` | 全机设备／功能行，必须覆盖以上十类 |

一行的格式如下（示意；不能用这一行替代整机清单）：

```json
{
  "id": "nic-2", "category": "network", "name": "第二个物理网口",
  "hardware_id": "本机 PCI vendor:device 和端口位置",
  "windows_ids": ["原始 Windows PNPDeviceID"],
  "observed": "PCI 可见，尚无网络接口", "driver_state": "missing",
  "status": "pending", "next_action": "查驱动与安装期设备屏蔽",
  "evidence": ["evidence/current-pci.txt"], "research": []
}
```

- `status`：`pending/repairing/waiting-user/deferred/passed/accepted-limit/not-applicable`。所有原设备行在后续版本保留；`id/category/hardware_id` 不换名掩盖旧问题，可新增发现项。
- `windows_ids`：物理网卡／GPU 对应原始 `PNPDeviceID`，每张单列。控制器从原 Windows 清单核对 PCI／USB 的 Net／Display 及 GPU，漏掉一个即拒绝；它不能发现原始采集从未发现的硬件，其他功能仍需覆盖审核。
- `passed` 增加 `test: {"kind":"functional","basis":"tool 或 human","result":"具体结果","evidence":"本轮结果文件"}`。`inspection`／`source-review` 不算功能通过。
- `accepted-limit` 需 `reason` 与 `acceptance`（用户明确接受该项限制的记录路径）。`not-applicable` 需 `reason` 与 `applicability`（不适用依据路径）；实际枚举的网卡／GPU 不能填不适用，用户决定不用也记具体限制。
- 未关闭项需 `next_action`。`repairing/deferred` 或 `repair_attempted=true` 需非空 `research`；每项为 `{"url":"https://原作者页面","finding":"适用条件／无支持／下载失败等实际发现","evidence":"查证记录路径"}`。
- 系统 build、驱动或运行 EFI 改变后，重新验证受影响项和基本连接／显示，更新配置快照与全文件清单；不继承未验证的“稳定”。

```text
python scripts/workflow.py --run "任务目录" --json record-devices --file "任务目录/evidence/devices-01.json"
python scripts/workflow.py --run "任务目录" --json status
```

`device_queue.next_item` 指出下一项，优先网络／GPU；等待用户和暂时无解项后置。整个清单仍开放时不能进入 07。逐项修复仍使用原 `select-source → problem/diagnose → repair-result`（实际故障需要诊断时），再登记新清单。phase 06 review 保留 `source_plans`、各项合同证据；`device_audit` 检查指向最新已登记清单。无须为了登记清单改动 A。

## 硬盘引导必须是一次完整交接

遵循 [06 硬盘引导操作](06-postinstall.md)。**复制文件、固件启动项、启动顺序和 OC 菜单是四件事**。不能只复制 EFI 或只设置 LauncherOption 就让用户拔盘试启动。

默认 UEFI 路线的 `boot-readiness-v1` 必需字段：

```json
{
  "schema": "boot-readiness-v1", "machine_uuid": "本任务 A UUID",
  "firmware_mode": "UEFI", "esp_guid": "目标硬盘 ESP GUID",
  "backup": "evidence/boot-backup.json", "authorization": "evidence/esp-scope.txt",
  "config": "evidence/esp-readback/OC/config.plist", "readback": "evidence/efi-hashes.json",
  "windows_preserved": "evidence/windows-boot-preserved.json",
  "registration_method": "实际执行的方法及工具版本",
  "variable_namespace": "EFI_GLOBAL_VARIABLE",
  "entry": {"id": "Boot0007", "active": true, "esp_guid": "同一目标硬盘 ESP GUID", "path": "\\EFI\\OC\\OpenCore.efi"},
  "boot_order": ["Boot0007", "Boot0000"], "boot_next": null,
  "firmware_readback": "evidence/decoded-firmware-boot-options.json"
}
```

示例启动号不是通用值。路径可为经过核验的 `\EFI\OC\OpenCore.efi` 或同一 ESP 的 OC `\EFI\BOOT\BOOTx64.efi`；不得指向 U 盘、覆盖 Windows bootmgfw.efi 或凭名字认启动项。回读必须核对真实固件命名空间，不能用被 OC 重定向的 BootOrder 冒充。Legacy／特殊链式引导先写单独的有据适配方案，当前 UEFI 门槛不接受伪装成已完成。

从 A 回读的配置须为 `Misc → Boot → ShowPicker=true`、`Timeout>=5`；第一次拔盘启动须有时间选系统。与 06 实测配置相比只允许菜单显示／等待、LauncherOption／LauncherPath 的迁移差异。硬件字段改变应返回测试，不能在迁移时顺便换驱动。全 EFI 文件差异另以 `readback` 清单逐件核对，配置校验不能代替 kext 二进制核对。

```text
python scripts/workflow.py --run "任务目录" --json boot-ready --file "任务目录/evidence/boot-ready-01.json"
```

通过后才给人一次拔盘冷启动指引。最终新报告在原登记信息上增加 `cold_boot`：`default_oc_observed=true`、`active_efi_evidence` 路径，以及 `macos/windows` 各自的 `{usb_removed:true,success:true,evidence:"本轮冷启动记录路径"}`；在 07 review 顶层以 `boot_manifest` 引用。冷启动实测不能使用 `accepted-limit` 跳过。备份、EFI 文件回读、真实启动项、BootOrder、两套系统均核对后才进入 08。

若启动项暂不能在 macOS 远程准确注册／读回，保留 U 盘，提前合并一次 BIOS Add Boot Option 或 UEFI Shell 现场操作，目标路径与磁盘必须填好；不承诺任意固件都能零人工。不得先让用户拔 U 盘启动 Windows，再补做本来缺失的启动项。

## 旧任务升级

已登记源码的旧任务用 `upgrade`。05/06 保留当前位置；旧版 07/08 回到 06 补验，旧审查存历史，磁盘实际内容不回滚、不格式化、已有有效实测可复用。完成新清单后再核对已有硬盘引导并补齐 07 证据，不要求无意义地重复安装或写盘。

控制器核对覆盖、状态、证据字节和配置关系，不能证明日志内容诚实或阻止 Agent 绕过工具直接操作。完整实机结果仍需本轮测试。
