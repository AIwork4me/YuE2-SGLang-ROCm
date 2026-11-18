#!/usr/bin/env python3
"""extract_archive_safe.py — fail-closed extraction for the campaign state archive.

Phase D/E gate: after the archive's size+SHA256 match the pins, extraction must
still refuse:
  * absolute member paths;
  * ".." traversal;
  * symlinks or hardlinks whose target resolves outside the destination;
  * device/fifo/special members;
  * overwriting an existing non-empty destination (P0: never clobber).

Usage:
  python extract_archive_safe.py --archive <tar.gz> --dest <dir> \
      [--expect-top <name>]   # e.g. armA_wsb_full
Exit 0 on success (writes extract_receipt.json next to the dest).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tarfile
import time
from pathlib import Path


def gzip_integrity_ok(path: Path) -> bool:
    try:
        with gzip.open(path, "rb") as f:
            while f.read(1 << 22):
                pass
        return True
    except (OSError, EOFError) as exc:
        print(f"FATAL: gzip integrity failed: {exc}")
        return False


def validate_members(tf: tarfile.TarFile, base: Path) -> list[str]:
    problems: list[str] = []
    base_str = str(base)
    for m in tf.getmembers():
        name = m.name
        if name.startswith("/") or name.startswith("\\"):
            problems.append(f"absolute path member: {name}")
            continue
        target = (base / name).resolve()
        if not str(target).startswith(base_str + "/"):
            problems.append(f"path traversal member: {name}")
            continue
        if m.issym() or m.islnk():
            link = (Path(name).parent / (m.linkname or "")).resolve()
            # resolve relative to the member's parent INSIDE the base
            link_abs = (base / Path(name).parent / (m.linkname or "")).resolve()
            if not str(link_abs).startswith(base_str + "/"):
                problems.append(f"unsafe link member: {name} -> {m.linkname}")
                continue
            _ = link
        if m.isdev() or m.isfifo():
            problems.append(f"special member rejected: {name} ({m.type})")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--expect-top", default=None,
                    help="expected single top-level directory inside the archive")
    args = ap.parse_args()

    if not args.archive.is_file():
        print(f"FATAL: archive missing: {args.archive}")
        return 2
    if not gzip_integrity_ok(args.archive):
        return 2

    args.dest.parent.mkdir(parents=True, exist_ok=True)
    if args.dest.exists() and any(args.dest.iterdir()):
        print(f"FATAL: destination not empty (P0 no-clobber): {args.dest}")
        return 3

    with tarfile.open(args.archive, "r:gz") as tf:
        problems = validate_members(tf, args.dest.resolve())
        if problems:
            print(f"FATAL: unsafe archive ({len(problems)} problems):")
            for p in problems[:20]:
                print(" -", p)
            return 4
        tops = {m.name.split("/")[0] for m in tf.getmembers() if m.name.strip()}
        if args.expect_top and tops != {args.expect_top}:
            print(f"FATAL: unexpected archive top level {sorted(tops)} "
                  f"!= [{args.expect_top}]")
            return 5
        n = 0
        t0 = time.time()
        for m in tf.getmembers():
            tf.extract(m, args.dest, filter="data",
                       set_attrs=False)
            n += 1
            if n % 200 == 0:
                print(f"  extracted {n} members...", flush=True)

    receipt = {
        "archive": str(args.archive),
        "dest": str(args.dest),
        "members": n,
        "top_level": sorted(tops),
        "extracted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_s": round(time.time() - t0, 1),
        "policy": "path-safety validated (no absolute/traversal/unsafe links/"
                  "specials); no-clobber enforced",
    }
    rcpt = args.dest.parent / (args.dest.name + ".extract_receipt.json")
    rcpt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
