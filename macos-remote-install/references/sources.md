# 原始资料与更新入口

整理日期 2026-10-29。下面是查证入口，执行时仍核对当前版本、适配范围和实际下载内容。历史指南可能落后于新驱动，不以搜索摘要覆盖原作者说明。记录「URL／查阅日期／版本或提交／支持证据／本机测试结果」。

## 工作流与工具格式

- [Agent Skills 规范](https://agentskills.io/specification)
- [WorkBuddy 技能结构](https://open.workbuddy.cn/docs/skill)
- [Windows OpenSSH 配置](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse)
- [Windows 防火墙规则配置与作用域](https://learn.microsoft.com/en-us/powershell/module/netsecurity/set-netfirewallrule)（SSH 配置流程于 2026-10-30 复核）
- [Windows OpenSSH 认证与服务器配置](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh-server-configuration)
- [OpenSSH 可选组件安装故障](https://learn.microsoft.com/en-us/troubleshoot/windows-server/system-management-components/cant-install-openssh-features)
- [Windows 本地空密码远程登录限制](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/security-policy-settings/accounts-limit-local-account-use-of-blank-passwords-to-console-logon-only)
- [Windows Hello PIN 与密码的区别](https://learn.microsoft.com/en-us/windows/security/identity-protection/hello-for-business/faq)
- [Windows OpenSSH 公钥管理](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)
- [Apple 远程登录](https://support.apple.com/guide/mac-help/allow-a-remote-computer-to-access-your-mac-mchlp1066/mac)

## OpenCore、恢复环境与硬件准备

- [OpenCorePkg 原作者仓库与发布](https://github.com/acidanthera/OpenCorePkg)：同版本 Configuration 文档、Sample.plist、ocvalidate、macrecovery。
- [OpenCore 官方文档入口](https://dortania.github.io/docs/)
- [OpenCore 安装指南](https://dortania.github.io/OpenCore-Install-Guide/)
- [Windows 制作安装介质](https://dortania.github.io/OpenCore-Install-Guide/installer-guide/windows-install.html)
- [安装阶段与重启](https://dortania.github.io/OpenCore-Install-Guide/installation/installation-process.html)
- [SSDTTime](https://github.com/corpnewt/SSDTTime)
- [USBToolBox 采集工具](https://github.com/USBToolBox/tool)
- [AMD-OSX 内核补丁](https://github.com/AMD-OSX/AMD_Vanilla)

## 驱动与排错

- [Acidanthera 项目](https://github.com/acidanthera)：在各项目仓库核对 Lilu、VirtualSMC、图形、音频等依赖及发布，不从未知整合包混装。
- [NullMoth NVIDIA 驱动](https://github.com/nullmoth/nvidia-macos-driver)
- [NVIDIA 支持与实测范围](https://github.com/nullmoth/nvidia-macos-driver/blob/main/docs/CARD-SUPPORT.md)
- [NVIDIA 排错](https://github.com/nullmoth/nvidia-macos-driver/blob/main/docs/TROUBLESHOOTING.md)
- [1401 安装器](https://github.com/nullmoth/1401)
- [OpenIntelWireless](https://github.com/OpenIntelWireless)：按 Wi-Fi 与蓝牙具体项目分别核对目标系统与依赖。
- [睡眠排错](https://dortania.github.io/OpenCore-Post-Install/universal/sleep.html)
- [键盘唤醒分类](https://dortania.github.io/OpenCore-Post-Install/usb/misc/keyboard.html)

Realtek／其他网卡的实验分支会变化，因此本包不把某个 fork 写为所有芯片的固定来源。Agent 用采集的 vendor/device/subsystem ID 查原作者 README、源码匹配表、目标 macOS 与发布记录，确认后记录准确仓库和提交。搜索不到可复核证据就报告未知，而不是编造驱动名称或地址。
