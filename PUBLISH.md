# 维护者发布说明

v0.2.8 处于公开测试阶段。本版变更与实测范围分别见[版本记录](CHANGELOG.md)和[验证记录](VALIDATION.md)。

项目仓库：[zxmls-ai/Hackintosh-skill](https://github.com/zxmls-ai/Hackintosh-skill)。以下步骤供维护者或希望建立自己分支仓库的用户参考；直接使用本项目可从 README 开始。

1. 在自己的 GitHub 账户中新建仓库，选择 Public；使用本包的 README 与 LICENSE，不需要再生成另一份模板。
2. 解压 `macos-remote-install-agent-v0.2.8.zip`。打开里面的 `macos-remote-install-agent` 文件夹，先查看 README.md 和 VALIDATION.md。
3. 在 GitHub 的上传文件页面上传该文件夹**里面的内容**，保持 README.md、LICENSE、macos-remote-install、tests、tools 等位于仓库根目录；不要只上传 ZIP，否则 Agent 不方便逐份读取。确认隐藏文件 .gitignore 与 .github 目录也包含在内。也可以用 GitHub Desktop 建立仓库并提交同样的文件。
4. 提交前检查文件列表，不能混入其他项目目录、runs、真实硬件报告、凭据、个人 EFI 或系统镜像。SOURCE-MANIFEST.json 是此次源码归档的清单，可保留；编辑源码后原清单不再代表新版本。
5. 确认 `downloads/` 包含本版 WorkBuddy ZIP 和对应 SHA256 清单。发布后打开仓库首页、技能入口和起步页，再下载公开的 WorkBuddy 包核对哈希。
6. 将仓库链接连同 README 里的启动提示发给 WorkBuddy＋DeepSeek。先验证只读采集和兼容性阶段，再按流程推进实际安装。

如另建 `v0.2.8` GitHub Release，可在说明中列出新手开场、现成方案优先和实测边界，并附两个 ZIP 和 SHA256SUMS.txt。仓库首页的 WorkBuddy 下载链接直接指向 `downloads/`。

这版有独立的 WorkBuddy frontmatter 适配包，但尚未在 WorkBuddy 客户端实测导入。若客户端没有相应入口，直接让 Agent 读取克隆目录中的 SKILL.md 即可，不需要先发布技能市场。

后续提交实机结果时，记录 Agent、模型、源码提交号和测试范围。不要因为同一台机器此前装成功，就把新的 AI 工作流标为“已全流程验证”。
