#!/usr/bin/env python3
"""Read-only Windows target identity plans. Never executes or authorizes disk writes."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
from agentkit import read_json, write_new, utc

BAD = {"", "unknown", "none", "null", "default string", "to be filled by o.e.m."}
PROTECTED = {"c12a7328-f81f-11d2-ba4b-00a0c93ec93b", "e3c9e316-0b5c-4db8-817d-f92df00215ae",
             "de94bba4-06d1-4d40-a16a-bfd50179d6ac"}


def identifier(value):
    s = str(value or "").strip().lower().strip("{}")
    compact = re.sub(r"[^a-z0-9]", "", s)
    return s if s not in BAD and compact and set(compact) not in ({"0"}, {"f"}) else ""


def host_and_freshness(inv):
    if inv.get("schema_version") != 1 or inv.get("platform") != "windows":
        raise ValueError("Expected Windows inventory schema v1")
    stamp = dt.datetime.fromisoformat(inv["captured_at_utc"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Inventory timestamp must include timezone")
    age = (dt.datetime.now(dt.timezone.utc) - stamp).total_seconds()
    if age < -60 or age > 600:
        raise ValueError("Inventory is stale or clock is wrong; collect again on A")
    host = identifier(inv["host"].get("uuid"))
    if not host:
        raise ValueError("Missing reliable host UUID; do not bypass identity checks")
    for e in inv.get("errors", []):
        if str(e.get("section", "")) in ("disk-list", "host"):
            raise ValueError("Incomplete target inventory: " + str(e.get("section")))
    return host


def target_complete(inv, disk):
    relevant = {f"disk-role-{disk['number']}", f"partition-role-{disk['number']}", f"partition-list-{disk['number']}"}
    for e in inv.get("errors", []):
        if e.get("section") in relevant:
            raise ValueError("Incomplete target inventory: " + str(e.get("section")))


def disk_identity(disk):
    keys = {"unique_id": identifier(disk.get("unique_id")), "serial": identifier(disk.get("serial"))}
    if not any(keys.values()) or not str(disk.get("model", "")).strip() or int(disk.get("size_bytes", 0)) <= 0:
        raise ValueError("Disk lacks stable identifiers/model/size")
    return {**keys, "model": str(disk["model"]).strip(), "size_bytes": int(disk["size_bytes"]),
            "bus_type": str(disk.get("bus_type", "")), "partition_style": str(disk.get("partition_style", ""))}


def layout(disk):
    if "partitions" not in disk:
        raise ValueError("Missing partition inventory")
    return sorted([{"guid": identifier(p.get("guid")), "offset_bytes": int(p["offset_bytes"]),
                    "size_bytes": int(p["size_bytes"]), "gpt_type": identifier(p.get("gpt_type")),
                    "is_boot": p.get("is_boot"), "is_system": p.get("is_system"),
                    "file_system": str(p.get("file_system", ""))} for p in disk["partitions"]],
                  key=lambda x: x["offset_bytes"])


def one(items, label):
    if len(items) != 1:
        raise ValueError(f"Expected one unambiguous {label}; got {len(items)}")
    return items[0]


def safe_purpose(disk, purpose, partition=None):
    if purpose == "usb":
        if disk.get("bus_type") != "USB" or disk.get("is_boot") is not False or disk.get("is_system") is not False:
            raise ValueError("USB target is not proven to be a non-system USB disk")
        if any(p.get("is_boot") is not False or p.get("is_system") is not False for p in disk["partitions"]):
            raise ValueError("USB contains a system/boot/unknown partition")
    else:
        if not partition:
            raise ValueError("Partition is required")
        if identifier(partition.get("gpt_type")) in PROTECTED or partition.get("is_system") is not False:
            raise ValueError("Protected/system/unknown partition refused")
        if purpose == "install-partition":
            if partition.get("is_boot") is not False or str(partition.get("drive_letter", "")).upper() == "C":
                raise ValueError("Refusing to designate Windows boot/C partition for erasure")
        elif purpose == "shrink":
            if str(partition.get("file_system", "")).upper() != "NTFS":
                raise ValueError("Shrink plan supports NTFS only")
        else:
            raise ValueError("Unknown purpose")


def make_plan(inv, number, purpose, partition=None):
    host = host_and_freshness(inv)
    disk = one([d for d in inv["disks"] if d["number"] == number], "disk number")
    target_complete(inv, disk)
    identity = disk_identity(disk)
    matches = []
    for candidate in inv["disks"]:
        try:
            if disk_identity(candidate) == identity:
                matches.append(candidate)
        except ValueError:
            continue
    one(matches, "disk identity")
    part = None if partition is None else one([p for p in disk["partitions"] if p["number"] == partition], "partition")
    if purpose == "usb" and partition is not None:
        raise ValueError("USB whole-device plan does not accept a partition argument")
    safe_purpose(disk, purpose, part)
    return {"schema_version": 1, "created_utc": utc(), "purpose": purpose, "host_uuid": host,
            "disk": identity, "layout": layout(disk), "observed_disk_number": number,
            "partition": None if part is None else {"guid": identifier(part.get("guid")),
              "offset_bytes": int(part["offset_bytes"]), "size_bytes": int(part["size_bytes"])},
            "authorization": "NONE: identity plan only; no backup or consent verification"}


def verify_plan(plan, inv):
    if plan.get("schema_version") != 1 or host_and_freshness(inv) != plan.get("host_uuid"):
        raise ValueError("Wrong host or plan schema")
    candidates = []
    for disk in inv["disks"]:
        try:
            if disk_identity(disk) == plan["disk"]:
                candidates.append(disk)
        except ValueError:
            continue
    disk = one(candidates, "physical disk")
    target_complete(inv, disk)
    if layout(disk) != plan["layout"]:
        raise ValueError("Partition layout/role/filesystem changed; reassess and create a new plan")
    part = None
    if plan["partition"] is not None:
        part = one([p for p in disk["partitions"] if
                    {"guid": identifier(p.get("guid")), "offset_bytes": int(p["offset_bytes"]),
                     "size_bytes": int(p["size_bytes"])} == plan["partition"]], "target partition")
    safe_purpose(disk, plan["purpose"], part)
    return {"identity_match": True, "current_disk_number": disk["number"],
            "current_partition_number": part["number"] if part else None,
            "warning": "NOT authorization. Recheck on A immediately before any approved write."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest="action", required=True)
    q = s.add_parser("make")
    q.add_argument("--inventory", required=True); q.add_argument("--disk", type=int, required=True)
    q.add_argument("--partition", type=int); q.add_argument("--purpose", choices=["usb", "install-partition", "shrink"], required=True)
    q.add_argument("--out", required=True)
    q = s.add_parser("verify"); q.add_argument("--plan", required=True); q.add_argument("--inventory", required=True)
    a = p.parse_args()
    try:
        inv = read_json(a.inventory)
        if a.action == "make":
            result = make_plan(inv, a.disk, a.purpose, a.partition)
            write_new(a.out, result)
        else:
            result = verify_plan(read_json(a.plan), inv)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as e:
        print(json.dumps({"identity_match": False, "error": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
