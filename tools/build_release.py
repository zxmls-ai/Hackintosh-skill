#!/usr/bin/env python3
"""Build public artifacts from an explicit allowlist. Never includes runs or credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "macos-remote-install"
sys.path.insert(0, str(SKILL / "scripts"))
from agentkit import no_link, sha

VERSION = "0.2.2"
REF_NAMES = ["00-controller", "01-remote-access", "02-hardware-routing", "03-storage", "04-installer",
             "05-boot-handoff", "06-postinstall", "07-troubleshooting", "08-state-and-tools",
             "case-14700k-4070ti-super", "sources"]
SOURCE_DOCS = [SKILL / "SKILL.md"] + [SKILL / "references" / (name + ".md") for name in REF_NAMES]
TOP_FILES = ["README.md", "START-HERE.md", "AI-GUIDE.md", "LICENSE", ".gitignore",
             "CONTRIBUTING.md", "TEST-FEEDBACK.md", "VALIDATION.md", "PUBLISH.md", "CHANGELOG.md"]
SCRIPTS = ["agentkit.py", "target_guard.py", "collect-windows.ps1", "collect-macos.sh", "enable-windows-ssh.ps1", "prepare_ssh_handoff.py", "workflow.py", "ssh_transport.py", "probe-windows.ps1"]
CODE = re.compile(r"(^```[^\n]*\n.*?^```[ \t]*$|`[^`\n]*`)", re.MULTILINE | re.DOTALL)


def sync_ssh_handoff():
    source = (SKILL / "scripts/enable-windows-ssh.ps1").read_text(encoding="utf-8-sig").rstrip()
    target = SKILL / "SKILL.md"
    text = target.read_text(encoding="utf-8")
    start, end = "<!-- windows-ssh-setup:start -->", "<!-- windows-ssh-setup:end -->"
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    target.write_text(before + start + "\n```powershell\n" + source + "\n```\n" + end + after, encoding="utf-8")


def body(text):
    return re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.S)


def make_guide():
    anchors = {p.resolve(): "section-" + p.stem.lower() for p in SOURCE_DOCS}
    content = ["# AI 远程协助安装 OpenCore 与 macOS：完整指南\n",
               f"版本 {VERSION}。此文件由 SKILL.md 与 references 合并生成。\n",
               "Agent 运行在 B，目标为 A。单文件可用于阅读和引导；配套脚本需取得完整仓库。没有工具时必须如实降级，不得编造执行结果。\n",
               "原文维护入口为仓库 macos-remote-install；本文中的脚本路径以该技能目录为工作目录。\n"]
    for p in SOURCE_DOCS:
        t = body(p.read_text(encoding="utf-8-sig"))
        title = next(line.lstrip("# ") for line in t.splitlines() if line.startswith("# "))
        content.append(f"- [{title}](#{anchors[p.resolve()]})")
    for p in SOURCE_DOCS:
        t = body(p.read_text(encoding="utf-8-sig"))
        def rewrite(match):
            label, link = match.groups()
            if "://" in link or link.startswith("#"):
                return match.group(0)
            target = (p.parent / link.split("#", 1)[0]).resolve()
            if target in anchors:
                return f"[{label}](#{anchors[target]})"
            if target.is_relative_to(ROOT):
                fragment = '#' + link.split('#',1)[1] if '#' in link else ''
                return f"[{label}]({target.relative_to(ROOT).as_posix()}{fragment})"
            return match.group(0)
        pieces = CODE.split(t)
        t = ''.join(part if index % 2 else re.sub(r"\[([^\]\n]+)\]\(([^)\n]+)\)", rewrite, part)
                    for index, part in enumerate(pieces))
        content.append(f'\n\n<a id="{anchors[p.resolve()]}"></a>\n\n{t}')
    (ROOT / "AI-GUIDE.md").write_text("\n".join(content).rstrip() + "\n", encoding="utf-8")


def workbuddy_skill():
    metadata = {"name": "macos-remote-install", "display_name": "AI 远程安装 OpenCore 与 macOS",
                "display_name_en": "Remote OpenCore and macOS Installation",
                "description": "从 B 电脑远程协助 A 电脑安装、排错和验收 macOS 双系统，先核对兼容性、备份与目标身份。",
                "description_zh": "固定流程与三项短交接；阶段 00 程序验收，异常处理后返回原步骤。",
                "description_en": "Guide a separate target PC through compatibility checks, backup, installation and evidence-based validation.",
                "version": VERSION, "author": "macos-remote-install contributors"}
    front = "---\n" + "\n".join(k + ": " + json.dumps(v, ensure_ascii=False) for k, v in metadata.items()) + "\n---\n\n"
    text = body((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    resource_index = "\n\n## WorkBuddy 子资源索引\n\n" + "\n".join("@references/" + n + ".md" for n in REF_NAMES)
    return (front + text + resource_index + "\n").encode("utf-8")


def source_files():
    selected = [ROOT / name for name in TOP_FILES] + SOURCE_DOCS
    selected += [SKILL / "scripts" / name for name in SCRIPTS]
    selected += [SKILL / "workflow.json", SKILL / "upgrades.json"]
    selected += [SKILL / "LICENSE", ROOT / "tests" / "test_helpers.py", ROOT / "tests" / "test_collect_windows.py", ROOT / "tests" / "test_ssh_handoff.py", ROOT / "tests" / "test_prepare_ssh_handoff.py",
                 ROOT / "tests" / "test_workflow.py", ROOT / "tools" / "build_release.py", ROOT / ".github" / "ISSUE_TEMPLATE" / "installation-feedback.md"]
    for p in selected:
        no_link(p)
        if not p.is_file(): raise ValueError(f"Missing public source file: {p.name}")
    return selected


def check_local_links(paths):
    for p in paths:
        if p.suffix != ".md": continue
        text = CODE.sub('', p.read_text(encoding="utf-8-sig"))
        for label, link in re.findall(r"\[([^\]\n]+)\]\(([^)\n]+)\)", text):
            if "://" in link or link.startswith(("#", "mailto:")): continue
            link = link.split("#", 1)[0]
            if not (p.parent / link).exists():
                raise ValueError(f"Broken local link in {p.name}: {link}")


def pack(path, entries):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in entries:
            z.writestr(name, data)
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None: raise ValueError("ZIP CRC validation failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    a = parser.parse_args()
    sync_ssh_handoff()
    make_guide()
    (SKILL / "LICENSE").write_bytes((ROOT / "LICENSE").read_bytes())
    paths = source_files()
    check_local_links(paths)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    no_link(a.out_dir)
    manifest = {"schema_version": 1, "version": VERSION, "algorithm": "sha256", "files": [
        {"path": p.relative_to(ROOT).as_posix(), **sha(p)} for p in paths]}
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (a.out_dir / "SOURCE-MANIFEST.json").write_bytes(manifest_data)
    repo_zip = a.out_dir / f"macos-remote-install-agent-v{VERSION}.zip"
    pack(repo_zip, [("macos-remote-install-agent/" + p.relative_to(ROOT).as_posix(), p.read_bytes()) for p in paths]
         + [("macos-remote-install-agent/SOURCE-MANIFEST.json", manifest_data)])
    wb_zip = a.out_dir / f"macos-remote-install-workbuddy-v{VERSION}.zip"
    pack(wb_zip, [(p.relative_to(ROOT).as_posix(), workbuddy_skill() if p == SKILL / "SKILL.md" else p.read_bytes())
                  for p in paths if SKILL in p.parents])
    sums = "\n".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name for p in (repo_zip, wb_zip)) + "\n"
    (a.out_dir / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    downloads = ROOT / "downloads"
    downloads.mkdir(exist_ok=True)
    no_link(downloads)
    (downloads / wb_zip.name).write_bytes(wb_zip.read_bytes())
    (downloads / "SHA256SUMS.txt").write_text(hashlib.sha256(wb_zip.read_bytes()).hexdigest() + "  " + wb_zip.name + "\n", encoding="utf-8")
    print(json.dumps({"public_file_count": len(paths), "repository_zip": str(repo_zip), "workbuddy_zip": str(wb_zip),
                      "crc_verified": True, "local_links_verified": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
