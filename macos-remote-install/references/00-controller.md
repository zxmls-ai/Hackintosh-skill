# 00 标准流程控制器

## 定位与实际覆盖

固定入口、输入、显示、阶段顺序和验收流程；AI 处理现场信息与未覆盖的故障。不要自行重写已有动作，也不要靠聊天里的“已完成”推进任务。

本版 `workflow.py` 在 B 实际执行阶段 00：生成固定 A 端代码、导入回传、核验 SSH 主机密钥、认证、查询 Windows 身份和管理员权限、SFTP 临时文件往返校验。成功后才进入 01。01～08 已有统一合同与顺序检查，具体操作仍由 Agent 按对应参考执行，报告标为人工／Agent 审核，不能声称这些阶段已全部自动化。硬件规则、用户判断和现场操作仍有必要。

标准模式需要 B 能运行 Python 3.10+ 和本包。只有阅读能力或不能执行工具时，明确标注“人工指导模式”，使用已有参考引导；不伪造控制器结果，也不把降级结果写为自动验收通过。

## Agent 的固定调用循环

以下命令均在 **B** 执行，工作目录为 `macos-remote-install`。用户只看 `display` 三项文字及当次确实要执行的完整代码，不看内部 JSON 和工具清单。

1. 取得并固定仓库快照，核对当前任务的 A/B 身份。首次使用运行 `init`；以后读 `status`，不重建任务。已有 v0.1 任务停在 `00-remote` 时可以就地初始化控制器，旧记录保留；其他阶段不得用初始化绕回 00。
2. 读取返回的 `next_action`，执行下面映射。不在正常分支自由规划步骤。
3. 每次操作后重新读取程序结果。按 `display` 原样显示；仅附具体的必要代码／选项。需要现场动作才等待用户，否则自动执行下一动作。
4. 用户自然语言先转换成当前允许的输入；无法确定的必填内容合并问一次，不把推测填成事实。用户提供的目标版本和密码取得方式保存在私有任务资料，不在后续阶段重复询问。
5. 失败先按错误码调用固定恢复分支；未覆盖时走本文的诊断流程。修复后重新验证当前步骤，不修改状态文件冒充通过。

```text
python scripts/workflow.py --run "B上的私有任务目录" --json init
python scripts/workflow.py --run "B上的私有任务目录" --json status
```

全局参数 `--run`、`--json` 放在动作名称前。任务目录由程序创建，也可接管既有 00 任务；不要放在 A 的待清空磁盘上。输出 `schema=workflow-output-v1`，其中 `phase/step/status/mode/revision/next_action` 给 Agent 使用，`display` 给用户显示。

| next_action | Agent 自动执行什么 |
|---|---|
| prepare-or-import | 有完整、来源已核实的 A 端连接结果则 import；没有才 prepare |
| import | 显示生成文件中的代码，等待用户一次回传；收到后保存结果并 import |
| verify | import 已提取密码时直接 verify；否则复用已有凭据参数，不额外询问或配置公钥 |
| upgrade | 新版核对登记过的旧版源哈希，备份并迁移原任务，再 status；不手改 sources |
| recover | 调用 recover 的固定规则；返回人工交接时才等待 |
| correct-input-then-resume | 使用用户已补充的正确凭据；没有新信息时合并询问一次，随后 resume → verify，禁止猜密码 |
| correct-input-then-import | 重新读取用户原始回传，必要时请其粘贴完整结果；不让用户重新安装 |
| correct-report-then-review | 按返回合同修正报告的缺项／证据引用并重交，不改实际设备、不冒充通过 |
| diagnose | 使用诊断流程，不能盲目反复 verify |
| repair-result | 在已有授权内执行已审阅方案并记录结果；必要的现场动作／新授权合并交接 |
| resume | 确认上次进程已结束，调用 resume 后重跑验收 |
| collect-acpi-then-review | 留在 03，按介质参考补齐真实原始表、配置与适配清单，再提交 review；不能以文字声明通过 |
| correct-efi-then-review | 留在 03，备份并修正首次启动的日志设置，更新 EFI 哈希与清单后重交；不重新分区 |
| guided-contract | 加载返回的阶段合同和对应参考，连续完成已授权操作，提交 review |
| none | 交付结果与已知限制 |

## 00 的一次交接

```text
python scripts/workflow.py --run "任务目录" --json prepare
```

程序尽力读取 B 的本机 IPv4，并通过本地绑定确认地址属于 B；无法取得时空数组表示未知。Agent 已用本机接口工具核对候选时，可重复传入 `--b-ip 实际地址`。不让用户查询 B 地址。网段比较仍只是线索，真实连通由 verify 验证。

将返回的 `script.path` 相对任务目录解析，读文件并逐字放入一个 PowerShell 代码块。告诉用户在 **A 的管理员 Windows PowerShell** 中粘贴运行。先提醒账户有非空密码（不是 PIN），一次回传含 `A_LOGIN_CREDENTIAL` 和 `SSH_HANDOFF_V1` 的复制块；用户在 B 的回复框替换第一行密码／密码文件路径占位后一起发送，已提供可填“已提供”。目标版本尚未提供时一并补充。不能让用户运行 B 上的控制器。

已有 SSH 只配置／校验，不重新安装；运行中的服务不重启。A 端脚本不保证睡眠或关机时仍然在线。

收到结果后，由 Agent 将两行一起保存到私有输入文件（不当作证据、不回显、不发布），并调用：

```text
python scripts/workflow.py --run "任务目录" --json import --file "结果文件.txt"
python scripts/workflow.py --run "任务目录" --json verify
```

默认账户取自 A 的回传。`A_LOGIN_CREDENTIAL: ` 后直接写密码或 B 上文件完整路径，不放进 JSON，不处理反斜杠／引号转义。路径可用双引号包住；密码形似路径时可写 `密码=实际密码`，显式路径可写 `文件=路径`。未替换占位或“已提供”不是密码，优先复用已有凭据，确实缺少才询问。import 自动把有效密码保存到任务的 `private/a-login-password`；verify 默认读取，不增加人工步骤。

密码文件支持 UTF-8／UTF-16 BOM、末尾换行；单行只含密码，保留密码本身空格。已有多行账号文件可包含唯一的 `密码：`、`登录密码：`、`Windows登录密码：` 或 `password:` 行；多条或不明确时不猜测。B 上已经取得的其他凭据仍可用 `verify --credential-file 路径`。用户已在当前会话提供密码时由 Agent 写入私有文件，不让用户另建文件。带密码的原始输入也属于私有凭据：不要放进 evidence、state、事件、命令行参数或公开包。已有可用的私钥可用 `--key-file` 替代，不能同时指定两种方式；加密私钥暂需现有客户端适配，不自动删除口令。

本版固定连接器使用 Paramiko。B 已具备时沿用；缺少会返回 `DEPENDENCY_MISSING`，`recover` 将已测试的 Paramiko 5.0.0 安装到本任务的 `runtime-deps`，不改全局 Python、不改 A。安装失败走诊断，不让用户盲目换认证方式。命令由 Agent 执行，用户不需要参与这些 B 端操作。

指纹必须来自用户在 A 执行得到的结果或独立核验的既有记录，不能先从未经核验的连接读一个指纹再自行编造回传。控制器只尝试结果中的地址，不扫描整个网段；主机密钥匹配前不会认证。密码错误停止该次验证，不在其他网口重复猜测。

实际验收：SSH 成功 → 主机／账户与回传一致 → 硬件 UUID 可识别 → 远程会话有管理员权限 → SFTP 在账户临时目录创建随机文件、回读一致、删除该文件。只发送固定只读探针，除这个临时文件外不在 A 写配置。重新连接同一任务时 UUID 必须与之前一致。通过后记录实际地址与证据，自动推进 01；未经实测的重启自启仍标为未测。

## 标准异常分支

```text
python scripts/workflow.py --run "任务目录" --json recover
```

- `DEPENDENCY_MISSING`：只安装 B 的私有依赖，随后重跑 verify。
- `SSH_TIMEOUT/SSH_REFUSED/SSH_UNREACHABLE`：不叠装、不换认证路线，重新生成固定的 A 端配置和检查块，一次回传当前 IP、服务、监听、防火墙与指纹；之前的地址可能已经变化。旧版 ≤0.2.1 的规则可能仍绑定 `Service=sshd`，新版配置块会显式改为 `Any`，并从有效策略复核；不需要重装 SSH 或改变服务 SID。如果已在外部完成这项修复且当前步骤仍允许 verify，复用现有可信回传与凭据直接 verify，不再要求用户重跑旧代码；已进入 diagnose 时先登记新修复证据再验收。若 A 装有 360、火绒、腾讯电脑管家等，检查其独立网络防护：优先放行 OpenSSH／TCP 22；无法放行时可由用户临时关闭网络防护重试，验证后恢复。不自动关闭安全软件；继续保留拦截可能导致连接失败。
- `HOST_KEY_MISMATCH`：不发送密码；从 A 获取新结果，检查重装／地址变化。不要关闭验证。新结果也要通过身份检查。
- `FINGERPRINT_READ_FAILED`：对比用户收到的代码与模板后交付固定代码；不卸载 SSH。仅有 `SETUP_FAILED` 时，原始错误仍由 Agent 从用户提供的私有文件检查，不能忽略组件来源或安装错误。
- `RESTART_REQUIRED`：告知保存工作并重启 A，再运行配置块；不自动重启未获授权的电脑。
- `AUTH_FAILED/CREDENTIAL_*`：暂停重复认证，检查用户名、密码类型及既有策略，得到更正信息后重跑。
- `ADMIN_REQUIRED/SFTP_*/REMOTE_*` 等：按错误分类收集证据，进入下述诊断流程。不能关闭 UAC、整个防火墙或指纹验证来绕过验收。

同一连接结果最多连续验证两次；同一固定恢复分支最多两轮。新地址结果或有新证据的修复可开始新的验证周期。达到限额进入诊断，不用新的文件名包装同一证据重置计数。

缺少凭据、密码文件不可读、B 缺少依赖都没有发起远端认证，不占用远端验证次数。密码已经发送而认证失败则计数；纠正凭据后仍达到限额时，用不含密码的用户更正记录作为新证据，登记诊断与处理结果后再验。

## 未覆盖问题的固定诊断流程

保存现场 → 收集新证据 → 一个可验证假设 → 备份／回退准备 → 按授权范围做最小调整 → 提交结果 → 重跑原验收。诊断方案是数据，不会被控制器传入 shell 或自动批准；Agent 执行方案前仍核对作用对象与权限。额外破坏性操作必须取得具体授权。

Agent 在私有任务目录准备以下 JSON，字符串描述尽量具体，路径相对任务目录：

```json
{"hypothesis":"基于日志的单一假设","target":"实际机器和配置对象","proposed_change":"最小调整","expected_result":"可观察结果","rollback":"恢复原配置的方法","evidence":["evidence/当前诊断证据.txt"]}
```

```text
python scripts/workflow.py --run "任务目录" --json diagnose --file "诊断方案.json"
```

执行或回退后提交结果，`outcome` 取 `applied/rolled-back/not-applied`。内容不能只有“成功”二字；证据需记录实际变化和观察。敏感值不进入这些文件。

```json
{"outcome":"applied","evidence":["evidence/实际处理结果.txt"]}
```

```text
python scripts/workflow.py --run "任务目录" --json repair-result --file "处理结果.json"
```

控制器只登记处理，返回 verify 或 prepare；不会因为 Agent 声明“修复成功”就通过 00。同内容证据不能重复重置尝试次数。无法解决时保留失败状态与可恢复现场，说明限制，不伪造下一阶段。

## 中断、重启与复测

进度写在 `workflow-state.json`，事件在 `workflow-events.jsonl`；`state.json` 只是兼容投影。`agentkit checkpoint` 拒绝修改受控任务的阶段。程序锁防止两个进程同时推进，进程退出后锁自动释放。

操作开始前记录 running。Agent／网络中断后先 status；未完成的操作运行 resume 后重验，不凭此前正在执行的提示认定成功。源文件哈希改变时拒绝静默续跑；保留固定仓库快照，不能直接手改 sources 解锁。v0.2.4 登记了 v0.2.0～v0.2.3 的源哈希及这些公开源码的 LF／CRLF 形式，00～04 的任务可用新版 `upgrade` 备份迁移；保留已经核验的 01／02 记录。≤0.2.2 旧任务已进 04 时，将旧 03 审核留作历史并回到 03 补验；0.2.3 的已验阶段不因本次哈希修复回退，不据此重做分区／格式化或中止正在进行的安装；正在运行、未知版本或修改过的源哈希会拒绝。阶段、身份、连接信息、失败计数和证据保留，不重新安装 SSH。

```text
python scripts/workflow.py --run "原任务目录" --json upgrade
python scripts/workflow.py --run "原任务目录" --json status
```

```text
python scripts/workflow.py --run "任务目录" --json resume
```

00 通过、尚未开始 01 的实机复测，可用 `recheck` 退回 00 验证，并保留机器 UUID。IP 变化时重新 import 新结果；不要换一个空任务绕开身份检查。关闭 PowerShell／Windows 重启后的测试合并到用户已经安排的操作，不额外要求重启。

```text
python scripts/workflow.py --run "任务目录" --json recheck
```

## 源码换行与升级

`.gitattributes` 固定本仓库文本检出的 LF。v0.2.4 的源码锁定只对显式登记的 UTF-8 文本做 CRLF→LF 后计算身份；不去掉 BOM、不裁剪空白、不重排 JSON，也不忽略代码改动。ACPI、EFI、备份、日志和验收证据仍按原始字节核对。这样 Windows `core.autocrlf` 不再导致相同源码被误判。[Git 换行属性](https://git-scm.com/docs/gitattributes)

旧任务的原始记录不要手改：新版 `upgrade` 只接受发布归档中预先登记的有限换行形式，完整备份旧状态并记录命中的变体，再切换到新源码身份。未知哈希仍拒绝，不可根据 Agent 猜测增补白名单／改 `sources`。已由其他工具手改过状态的任务要保留改前文件和取证记录，不能把它描述成原控制器自动迁移。升级失败时核对版本、实际内容和证据，不能“为了通过”重算记录。

## 01～08 的统一合同

完整规则位于 [workflow.json](../workflow.json)：每阶段含输入、前置条件、标准动作、检查项、异常入口、恢复位置和唯一下一阶段。阶段 01 的实机工作从固定硬件采集开始，不需要让用户先回复“继续”。

03 额外有文件级门槛：`acpi_tables` 必须为 pass 且指定 `manifest`（相对任务目录的 `acpi-evidence-v1` JSON）；控制器检查 DSDT/SSDT 文件的结构、长度、校验和与哈希，核对目标 UUID、当前配置、启用的 ACPI 文件及适配记录。文字声明或空文件不能通过；`accepted-limit` 不能绕过这个门槛。`firmware_config_review` 仍需实际配置与固件依据，不能把读到表等同于 Booter 配置正确。具体格式见介质参考。

这些阶段的操作还不是完整自动执行器。Agent 依合同与对应参考工作，保存原始工具输出／人工观察／来源资料。完成当前合同后，按返回的 `verification` 名称提交报告：

阶段 00 的验证会关闭其连接；后续合同模式可使用现有 SSH/SFTP 客户端，或适配相同库的传输调用，按已保存的指纹和机器身份重新连接，执行包内采集器和对应阶段已授权的动作。禁止另写连接器替代 00 验收的约束仅针对 00；后续不得关闭指纹验证、重新索取已有密码或虚构持久会话。

合同执行中遇到实际故障，Agent 保存证据后调用 `problem --file 故障记录.json`；故障记录形如 `{"code":"BOOT_PANIC","evidence":["evidence/启动照片.png"]}`。再按 `diagnose → repair-result` 处理，回到同一合同重验，不推进阶段。仅报告格式错误走 `correct-report-then-review`，无需修改设备。

```json
{"phase":"当前阶段 ID","checks":{"当前合同的一项检查":{"result":"pass","basis":"tool","evidence":["evidence/实际证据.json"]}}}
```

实际报告必须包含当前合同全部检查项。`basis` 取 `tool/human/source-review`；功能确有限制时用 `accepted-limit`，并附 `user_acceptance` 的真实授权记录。磁盘身份、授权、备份内容与恢复抽查等不可作为限制跳过。未通过或未测试不能写 pass。用户未要求的可选功能，记录“不适用”的依据与用户确认，使用限制结果而不虚构实测。

```text
python scripts/workflow.py --run "任务目录" --json review --file "阶段检查.json"
```

控制器检查顺序、完整性和证据哈希，明确标为 `agent-and-human-reviewed; not automatically verified`。它不能证明任意日志语义正确，更不能保证任何 Agent 都不会绕过规则。后续将根据实机反馈逐步用专用执行器替换这部分人工判断；当前不要宣称全程无人值守或所有机型兼容。
