# 08 状态、进度和配套工具

v0.2 标准模式以 [流程控制器](00-controller.md) 为唯一推进入口；先 `init/status`，按其结果调用动作。下列基础工具继续用于采集、清单与文件校验，不具有覆盖控制器阶段的权限。

## 任务目录

在 B 的独立目录中保存；不要放进将格式化的 A 分区或 U 盘。

```text
runs/任务名/
  workflow-state.json    标准模式的实际状态、步骤、源版本与验收证据
  workflow-events.jsonl  标准动作与阶段事件
  state.json             当前阶段、A/B 身份记录、限制和下一步
  journal.jsonl          逐次检查点与证据摘要
  NEXT.md                重启／人工交接的当前指引
  inventory/             Windows/macOS 采集与目标计划
  evidence/              日志、截图、版本来源与测试结果
  backups/               已校验的备份，必要时只存外部备份的清单
  staging/               未部署的 EFI、下载及目标专用脚本
```

任务目录是本次安装的私有数据，不作为发布包。机器硬件 ID、文件清单、截图也可能含隐私，分享前脱敏。账号密码、私钥、Apple ID、BitLocker 恢复密钥不写 state/journal；凭据引用只记录获取机制，不复制内容。

`state.json` 至少维护：任务模式、当前阶段、状态、最后检查点、A/B 身份的证据引用、目标 OS、已有授权范围的原话和时间、磁盘计划引用、组件版本记录、最近可用 EFI、未解决问题、下一步。状态工具只管理其中基本字段；其余由 Agent 用结构化文件保存并引用，不把自由文本指令交给自动 shell 执行。

旧模式的基础状态为 planned/running/waiting_user/verified/failed/limited。标准模式由控制器管理，另有 waiting_agent/reviewed；00 的成功需要固定连接器真实运行，后续合同审核明确区别于自动验收。不得由 Agent 自行设置 verified。

## 工具命令

以下以技能目录为工作目录，B 已有真实可用的 Python 3.10+。路径带空格时按当前 shell 正确引用；尖括号参数先替换。

```text
python scripts/agentkit.py preflight
python scripts/agentkit.py init --run <新的任务目录>
python scripts/workflow.py --run <任务目录> --json status
python scripts/agentkit.py manifest --root <源文件范围目录> --out <范围外的清单文件.json>
python scripts/agentkit.py verify-manifest --root <备份目录> --manifest <源文件清单.json>
python scripts/agentkit.py check-efi --root <准备中的EFI目录>
```

- preflight 不联网或检查 A，只报告 B 的运行时和可用工具路径。
- init 拒绝覆盖已有任务。已有任务直接读取状态并核验现场；不可因为工具拒绝而清空旧目录。
- 旧模式 checkpoint 仅核对证据文件，不判断语义；受控任务禁止使用它推进。标准模式使用专用验证动作／合同 review。重启人工指引仍同步到 NEXT.md，不能把计划当作验收证据。
- manifest 遍历普通文件并计算 SHA256，拒绝符号链接／Windows reparse point 和遍历时发生变化的文件；输出必须在源范围之外。大数据量任务应分批并告知进度，不让长时间哈希阻塞对话。
- verify-manifest 检查源清单中的所有文件、大小与哈希；目标多出的文件会报告，但本工具不会删除。对于专门的 EFI staging，额外文件也应审查，不能只看哈希一致。
- check-efi 验证 X64 基础布局和启用项的引用，不修改文件；必须另运行同版本 ocvalidate。它不检查驱动可信性、补丁硬件匹配、CPU/OS 兼容或启动项注册。

`target_guard.py` 仅在 Windows 采集格式上工作，命令见 [03 存储](03-storage.md)。它要求最近 10 分钟内的采集时间并进行稳定身份匹配；跨 Windows/macOS 时重新依据实际 diskutil 信息映射。操作执行前仍要在 A 再核对，避免采集后有人拔插磁盘。

`collect-windows.ps1 -OutputPath <绝对路径>` 在 A 的 Windows 运行，不要在 B 运行后把结果当成 A。其系统查询为只读，只写指定报告文件。管理员权限能提供更完整数据；失败字段集中记录，不能按空数组推定无设备。

`sh collect-macos.sh <新的输出绝对目录>` 在 A 的 macOS 运行，拒绝非 Darwin 和已有输出目录。它读取系统／磁盘／驱动／电源状态并保存报告，不挂载或修改 ESP，不修改电源参数。部分日志可能需要管理员权限，退出码写在目录中。

单文件指南模式下如果脚本不可访问，明确说明，使用系统工具实现相同检查或请用户提供完整包。不要运行不存在的脚本、编造输出，或为了继续而省略目标身份校验。

## 每次交接只用三项

```text
进度：03 安装介质｜EFI 已校验，恢复镜像已下载。
下一步：写入并核验安装 U 盘。
需要你：把 U 盘插到 A；识别后会告知具体清空目标。
```

默认每项一两句、正文约 150 字以内（必需代码／连接结果除外）。无需人工动作时写“无需操作，我继续”并继续执行，不能停下等待“继续”。详细工具清单、哈希、证据路径和推理留在 state/journal/evidence；不把内部检查点逐条输出给用户。

可以合并的同阶段查询、校验、下载和操作自动连续完成；不能合并尚未确认对象的清空动作。确认时只展示具体目标、容量、影响与备份状态，不用整张内部表淹没用户。重启交接只给本次按键／菜单、预期画面及异常时拍照回报方式；完整回退记录留在 NEXT.md。

阶段 00 正常只需一次 A 端脚本与一次完整结果回传。成功回传复制块在 `SSH_HANDOFF_V1` 前加入 `A_LOGIN_CREDENTIAL` 占位，用户替换为密码或 B 上的文件路径，一次发送。B 将原文作为私有凭据输入，import 提取凭据到 private；状态／证据只保留清洗后的连接信息，再自动完成后续检查，不额外要求用户查询 IP、用户名和指纹。

下载使用真实字节数；安装阶段使用实际日志活动。长任务安排可恢复的后台执行与输出位置，而不是固定等待后宣称完成。

新 Agent 接手时先检查任务状态、最后日志和实际机器。重启后驱动加载、IP、磁盘编号、EFI 挂载路径都可能变化。记录不是现场的替代。
