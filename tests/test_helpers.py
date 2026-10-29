"""Synthetic tests only. Never connects to or alters the installation target."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "macos-remote-install" / "scripts"))
import agentkit as kit
import target_guard as guard


def inventory():
    return {"schema_version": 1, "platform": "windows", "captured_at_utc": kit.utc(),
            "host": {"uuid": "synthetic-target-a"}, "errors": [], "disks": [
                {"number": 3, "unique_id": "synthetic-usb-id", "serial": "test-stick", "model": "Synthetic USB",
                 "size_bytes": 16000000000, "bus_type": "USB", "partition_style": "GPT", "is_boot": False, "is_system": False,
                 "partitions": [{"number": 1, "guid": "synthetic-partition", "offset_bytes": 1048576,
                                  "size_bytes": 8000000000, "gpt_type": "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7",
                                  "drive_letter": "U", "file_system": "NTFS", "is_boot": False, "is_system": False}]}]}


class TargetTests(unittest.TestCase):
    def test_disk_number_change_is_reported(self):
        inv = inventory(); plan = guard.make_plan(inv, 3, "usb")
        inv["disks"][0]["number"] = 8
        self.assertEqual(guard.verify_plan(plan, inv)["current_disk_number"], 8)

    def test_wrong_host_rejected(self):
        inv = inventory(); plan = guard.make_plan(inv, 3, "usb")
        inv["host"]["uuid"] = "synthetic-machine-b"
        with self.assertRaises(ValueError): guard.verify_plan(plan, inv)

    def test_replacement_same_number_same_capacity_rejected(self):
        inv = inventory(); plan = guard.make_plan(inv, 3, "usb")
        inv["disks"][0]["serial"] = "replacement-stick"
        with self.assertRaises(ValueError): guard.verify_plan(plan, inv)

    def test_changed_partition_rejected(self):
        inv = inventory(); plan = guard.make_plan(inv, 3, "usb")
        inv["disks"][0]["partitions"][0]["size_bytes"] -= 1024
        with self.assertRaises(ValueError): guard.verify_plan(plan, inv)

    def test_system_usb_rejected(self):
        inv = inventory(); inv["disks"][0]["is_system"] = True
        with self.assertRaises(ValueError): guard.make_plan(inv, 3, "usb")

    def test_unknown_boot_flag_rejected(self):
        inv = inventory(); del inv["disks"][0]["partitions"][0]["is_boot"]
        with self.assertRaises(ValueError): guard.make_plan(inv, 3, "usb")

    def test_missing_id_rejected(self):
        inv = inventory(); inv["disks"][0].update(unique_id="000000", serial="Unknown")
        with self.assertRaises(ValueError): guard.make_plan(inv, 3, "usb")

    def test_stale_report_rejected(self):
        inv = inventory(); inv["captured_at_utc"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
        with self.assertRaises(ValueError): guard.make_plan(inv, 3, "usb")

    def test_ambiguous_clone_rejected(self):
        inv = inventory(); inv["disks"].append(copy.deepcopy(inv["disks"][0])); inv["disks"][1]["number"] = 7
        with self.assertRaises(ValueError): guard.make_plan(inv, 3, "usb")

    def test_esp_erasure_rejected(self):
        inv = inventory(); inv["disks"][0]["partitions"][0]["gpt_type"] = "{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}"
        with self.assertRaises(ValueError): guard.make_plan(inv, 3, "install-partition", 1)

    def test_windows_can_shrink_but_not_be_erased(self):
        inv = inventory(); inv["disks"][0]["partitions"][0].update(drive_letter="C", is_boot=True)
        with self.assertRaises(ValueError): guard.make_plan(inv, 3, "install-partition", 1)
        self.assertEqual(guard.make_plan(inv, 3, "shrink", 1)["purpose"], "shrink")

    def test_incomplete_disk_query_rejected(self):
        inv = inventory(); inv["errors"] = [{"section": "partition-list-3", "message": "denied"}]
        with self.assertRaises(ValueError): guard.make_plan(inv, 3, "usb")

    def test_unrelated_empty_reader_does_not_block_valid_target(self):
        inv = inventory(); inv["disks"].append({"number": 9, "model": "empty reader", "size_bytes": 0})
        self.assertEqual(guard.make_plan(inv, 3, "usb")["observed_disk_number"], 3)


class FilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()

    def test_backup_tampering_detected_and_extras_preserved(self):
        src = self.root / "source"; src.mkdir(); (src / "中文.txt").write_text("original", encoding="utf-8")
        manifest = self.root / "manifest.json"; kit.make_manifest(src, manifest)
        self.assertTrue(kit.verify_manifest(src, manifest)["ok"])
        (src / "extra.txt").write_text("keep", encoding="utf-8")
        self.assertEqual(kit.verify_manifest(src, manifest)["extra_files"], ["extra.txt"])
        (src / "中文.txt").write_text("tampered", encoding="utf-8")
        self.assertFalse(kit.verify_manifest(src, manifest)["ok"])
        self.assertTrue((src / "extra.txt").exists())

    def test_manifest_traversal_rejected(self):
        manifest = self.root / "manifest.json"
        kit.write_new(manifest, {"schema_version": 1, "algorithm": "sha256", "files": [{"path": "../outside", "size": 0, "sha256": "x"}]})
        with self.assertRaises(ValueError): kit.verify_manifest(self.root, manifest)

    def test_unreadable_subdirectory_cannot_be_silently_excluded(self):
        src = self.root / "source"; src.mkdir(); restricted = src / "restricted"; restricted.mkdir()
        (src / "visible.txt").write_text("visible", encoding="utf-8")
        (restricted / "important.txt").write_text("must back up", encoding="utf-8")
        manifest = self.root / "manifest.json"
        original = os.scandir
        def denied(path):
            if Path(path) == restricted: raise PermissionError("synthetic access denied")
            return original(path)
        with mock.patch("os.scandir", side_effect=denied):
            with self.assertRaises(PermissionError): kit.make_manifest(src, manifest)
        self.assertFalse(manifest.exists())
        kit.make_manifest(src, manifest)
        with mock.patch("os.scandir", side_effect=denied):
            with self.assertRaises(PermissionError): kit.verify_manifest(src, manifest)

    def test_manifest_self_inclusion_and_overwrite_rejected(self):
        with self.assertRaises(ValueError): kit.make_manifest(self.root, self.root / "manifest.json")
        existing = self.root / "existing.json"; existing.write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError): kit.write_new(existing, {})

    def test_links_refused(self):
        actual = self.root / "actual"; actual.write_text("keep", encoding="utf-8")
        link = self.root / "link"
        try: link.symlink_to(actual)
        except OSError: self.skipTest("OS/user does not allow symlink creation")
        with self.assertRaises(ValueError): kit.sha(link)

    def test_checkpoint_requires_real_local_evidence(self):
        run = self.root / "run"; kit.init_run(run)
        with self.assertRaises(ValueError): kit.checkpoint(run, "06-gpu", "verified", "done", [])
        with self.assertRaises(OSError): kit.checkpoint(run, "06-gpu", "verified", "done", ["missing.txt"])
        with self.assertRaises(ValueError): kit.checkpoint(run, "06-gpu", "verified", "done", ["../outside.txt"])
        (run / "evidence" / "check.txt").write_text("synthetic test output", encoding="utf-8")
        kit.checkpoint(run, "06-gpu", "verified", "synthetic only", ["evidence/check.txt"])
        self.assertEqual(kit.read_json(run / "state.json")["last_checkpoint"]["summary"], "synthetic only")
        self.assertEqual(len((run / "journal.jsonl").read_text(encoding="utf-8").splitlines()), 1)

    def test_resume_does_not_overwrite_state(self):
        run = self.root / "run"; kit.init_run(run)
        original = (run / "state.json").read_bytes()
        with self.assertRaises(FileExistsError): kit.init_run(run)
        self.assertEqual(original, (run / "state.json").read_bytes())

    def test_efi_references_and_disabled_entries(self):
        efi = self.root / "EFI"
        for name in ("BOOT/BOOTx64.efi", "OC/OpenCore.efi", "OC/ACPI/Test.aml"):
            p = efi / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"synthetic")
        config = {"ACPI": {"Add": [{"Enabled": True, "Path": "Test.aml"}, {"Enabled": False, "Path": "Missing.aml"}]}}
        with (efi / "OC/config.plist").open("wb") as f: plistlib.dump(config, f)
        self.assertTrue(kit.check_efi(efi)["ok"])
        (efi / "OC/ACPI/Test.aml").unlink()
        self.assertFalse(kit.check_efi(efi)["ok"])

    def test_efi_path_escape_rejected(self):
        efi = self.root / "EFI"
        for name in ("BOOT/BOOTx64.efi", "OC/OpenCore.efi"):
            p = efi / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"synthetic")
        with (efi / "OC/config.plist").open("wb") as f:
            plistlib.dump({"UEFI": {"Drivers": [{"Enabled": True, "Path": "../../outside.efi"}]}}, f)
        self.assertFalse(kit.check_efi(efi)["ok"])


if __name__ == "__main__": unittest.main()
