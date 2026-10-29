#!/usr/bin/env python3
"""Portable local helpers. No SSH, disk mutations, downloads, or driver installation."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import shutil
import stat
import sys
import tempfile

VERSION = "0.1.0"


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_new(path, data):
    with Path(path).open("x", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def no_link(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        s = item.lstat()
        if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Link/reparse point refused: {item}")


def confined(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Expected a portable relative path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or any(x in ("..", ".") for x in relative.split("/")):
        raise ValueError("Path traversal refused")
    root = Path(root).resolve()
    candidate = root.joinpath(*parts.parts)
    candidate.resolve().relative_to(root)
    return candidate


def sha(path):
    no_link(path)
    before = Path(path).stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Not a regular file: {path}")
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    after = Path(path).stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError(f"File changed while hashing: {path}")
    return {"size": before.st_size, "sha256": h.hexdigest()}


def files(root):
    root = Path(root).absolute()
    no_link(root)
    if not root.is_dir():
        raise ValueError("Root must be a directory")
    found = []
    def fail_walk(error):
        raise error
    for parent, directories, names in os.walk(root, followlinks=False, onerror=fail_walk):
        for name in directories + names:
            no_link(Path(parent) / name)
        for name in names:
            p = Path(parent) / name
            if not p.is_file():
                raise ValueError(f"Non-regular entry: {p}")
            found.append(p)
    return sorted(found)


def make_manifest(root, out):
    root = Path(root).absolute()
    out = Path(out).absolute()
    try:
        out.resolve().relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("Manifest output must be outside the source tree")
    initial = files(root)
    entries = [{"path": p.relative_to(root).as_posix(), **sha(p)} for p in initial]
    if initial != files(root):
        raise ValueError("Source file list changed during hashing")
    result = {"schema_version": 1, "created_utc": utc(), "algorithm": "sha256", "files": entries}
    write_new(out, result)
    return {"manifest": str(out), "file_count": len(entries)}


def verify_manifest(root, manifest):
    data = read_json(manifest)
    if data.get("schema_version") != 1 or data.get("algorithm") != "sha256":
        raise ValueError("Unsupported manifest")
    seen, failures = set(), []
    for entry in data["files"]:
        rel = entry["path"]
        if rel.casefold() in seen:
            raise ValueError("Duplicate/case-colliding manifest path")
        seen.add(rel.casefold())
        p = confined(root, rel)
        try:
            actual = sha(p)
            if actual != {"size": entry["size"], "sha256": entry["sha256"]}:
                failures.append({"path": rel, "error": "content mismatch"})
        except (OSError, ValueError) as e:
            failures.append({"path": rel, "error": str(e)})
    extras = [p.relative_to(Path(root).absolute()).as_posix() for p in files(root)
              if p.relative_to(Path(root).absolute()).as_posix().casefold() not in seen]
    return {"ok": not failures, "failures": failures, "extra_files": extras,
            "meaning": "Content verification only; not a restore or boot test"}


def init_run(run):
    run = Path(run)
    if not run.parent.is_dir():
        raise ValueError("Create the intended parent directory first")
    no_link(run.parent)
    run.mkdir(exist_ok=False)
    for name in ("inventory", "evidence", "backups", "staging"):
        (run / name).mkdir()
    write_new(run / "state.json", {"schema_version": 1, "tool_version": VERSION,
              "created_utc": utc(), "mode": "undecided", "phase": "00-remote", "status": "planned",
              "machine_a": None, "machine_b": None, "last_checkpoint": None,
              "unresolved": [], "next_action": "Verify agent capabilities and A/B identities"})
    (run / "journal.jsonl").write_text("", encoding="utf-8")
    (run / "NEXT.md").write_text("# Next handoff\n\nNo installation operation has been authorized or executed by this helper.\n", encoding="utf-8")
    return {"run": str(run.resolve()), "created": True}


def checkpoint(run, phase, status, summary, evidence):
    run = Path(run).absolute()
    no_link(run)
    if not phase or not summary:
        raise ValueError("Phase and summary are required")
    if status not in ("planned", "running", "waiting_user", "verified", "failed", "limited"):
        raise ValueError("Unsupported status")
    if status == "verified" and not evidence:
        raise ValueError("Verified requires evidence files; agent must judge their meaning")
    proofs = [{"path": rel, **sha(confined(run, rel))} for rel in evidence]
    state_path = run / "state.json"
    no_link(state_path)
    no_link(run / "journal.jsonl")
    state = read_json(state_path)
    event = {"timestamp_utc": utc(), "phase": phase, "status": status, "summary": summary, "evidence": proofs}
    state.update(phase=phase, status=status, last_checkpoint=event)
    # Journal first: if interrupted before replacing state, the event remains recoverable.
    with (run / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    fd, name = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=run)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, state_path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return event


def check_efi(root):
    root = Path(root).absolute()
    no_link(root)
    errors, warnings, checked = [], [], []

    def require(rel):
        try:
            p = confined(root, rel)
            no_link(p)
            if not p.is_file() or not p.stat().st_size:
                raise ValueError("Missing or empty file")
            checked.append(rel)
        except (OSError, ValueError) as e:
            errors.append({"path": rel, "error": str(e)})

    for p in ("BOOT/BOOTx64.efi", "OC/OpenCore.efi", "OC/config.plist"):
        require(p)
    config = confined(root, "OC/config.plist")
    if config.is_file() and not any(e.get("path") == "OC/config.plist" for e in errors):
        try:
            with config.open("rb") as f:
                c = plistlib.load(f)
            seen = set()
            for group, entries in (("ACPI", c.get("ACPI", {}).get("Add", [])),
                                   ("UEFI", c.get("UEFI", {}).get("Drivers", [])),
                                   ("Kernel", c.get("Kernel", {}).get("Add", []))):
                for e in entries:
                    if not isinstance(e, dict):
                        errors.append({"group": group, "error": "Unsupported legacy entry; use matching OC validator"})
                        continue
                    if not e.get("Enabled", False):
                        continue
                    key = e.get("BundlePath" if group == "Kernel" else "Path", "")
                    if not key or (group, key.casefold()) in seen:
                        errors.append({"group": group, "error": "Missing or duplicate enabled path", "path": key})
                        continue
                    seen.add((group, key.casefold()))
                    if group == "Kernel":
                        base = f"OC/Kexts/{key}"
                        info = e.get("PlistPath", "")
                        if not info:
                            errors.append({"path": base, "error": "Missing PlistPath"})
                        else:
                            require(f"{base}/{info}")
                        executable = e.get("ExecutablePath", "")
                        if executable:
                            require(f"{base}/{executable}")
                    else:
                        require(f"OC/{'ACPI' if group == 'ACPI' else 'Drivers'}/{key}")
            for e in c.get("Misc", {}).get("Tools", []):
                if isinstance(e, dict) and e.get("Enabled"):
                    require("OC/Tools/" + e.get("Path", ""))
        except (ValueError, TypeError, AttributeError, plistlib.InvalidFileException) as e:
            errors.append({"path": "OC/config.plist", "error": str(e)})
    warnings.append("Run matching ocvalidate separately. This does not validate compatibility or bootability.")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "checked_paths": checked}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    q = sub.add_parser("init"); q.add_argument("--run", required=True)
    q = sub.add_parser("checkpoint")
    for name in ("run", "phase", "status", "summary"):
        q.add_argument("--" + name, required=True)
    q.add_argument("--evidence", action="append", default=[])
    q = sub.add_parser("manifest"); q.add_argument("--root", required=True); q.add_argument("--out", required=True)
    q = sub.add_parser("verify-manifest"); q.add_argument("--root", required=True); q.add_argument("--manifest", required=True)
    q = sub.add_parser("check-efi"); q.add_argument("--root", required=True)
    a = p.parse_args()
    try:
        if a.command == "preflight":
            result = {"version": VERSION, "role": "B only", "platform": platform.platform(),
                      "python": sys.version, "executable": sys.executable,
                      "tools": {x: shutil.which(x) for x in ("ssh", "sftp", "git", "powershell", "pwsh", "curl")},
                      "note": "Tool paths do not prove SSH/network permissions. No connection attempted."}
        elif a.command == "init": result = init_run(a.run)
        elif a.command == "checkpoint": result = checkpoint(a.run, a.phase, a.status, a.summary, a.evidence)
        elif a.command == "manifest": result = make_manifest(a.root, a.out)
        elif a.command == "verify-manifest": result = verify_manifest(a.root, a.manifest)
        else: result = check_efi(a.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok", True) else 1
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
