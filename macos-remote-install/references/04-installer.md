# 04 下载、组装 EFI 与制作安装介质

## 锁定版本与来源

按硬件报告选择 macOS 和 OC 组合。在任务目录记录每项 URL、标签／提交、下载时间、SHA256、用途、适配范围和校验证据。优先官方稳定发布；实验构建注明原因。镜像站只解决传输问题，不能替代原作者来源核对。不把“最新”作为固定版本号，也不擅自升级安装中已锁定的组件。

OpenCore 程序、OpenRuntime、Sample.plist、Configuration 文档和 ocvalidate 来自**同一个发布包**。恢复镜像从 Apple 服务获取，可使用该 OC 包中的 macrecovery；先看当前 `--help` 与文档再选 board-id／参数。不要凭记忆复制“latest”等于 Sequoia 的老命令。下载后验证实际镜像版本与对应 chunklist；镜像版本和最终联网安装的完整系统版本分别记录。[Windows 制作介质](https://dortania.github.io/OpenCore-Install-Guide/installer-guide/windows-install.html)

恢复镜像是安装恢复环境，不是完整离线系统镜像，也不是 BIOS 固件。恢复环境联网必须可用，否则先准备可用网卡／驱动或明确的离线安装方案。若用户指定精确小版本但 Apple 恢复服务器不提供，说明实际可取得版本，不静默替换。

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
