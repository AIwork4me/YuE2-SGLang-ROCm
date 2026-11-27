#!/usr/bin/env python3
"""rc6_evidence_freeze.py — M0.3: SHA256-freeze the frozen scientific evidence.

Hashes every file of the protected RC5.1 evidence set (the 384 generated
FLACs + identity chain + frozen evaluator receipts + Q3O receipts + the
same-host backup volume manifests/archives) so that any later mutation by
RC6 work is detectable. Read-only: never writes into the evidence trees.

Usage:
  python3 scripts/rc6_evidence_freeze.py --out reports/developer_reference/00_EVIDENCE_FREEZE.json \
      [--verify PREVIOUS.json]   # re-verify a previous freeze instead of writing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Frozen trees (absent ones are reported, never fatal — freeze must state
# exactly what exists).
EVIDENCE_TREES = [
    ("rc5_1_reports", REPO / "reports/w7900_rc5/rc5_1"),
    ("rc5_5_reports", REPO / "reports/w7900_rc5"),  # non-rc5_1 files only counted
    ("historical_armB_manifest", REPO / "evidence/publication/armB_campaign"),
    ("rc5_run_primary", Path("/data/yue2-runs/rc5-latest-upstream-20261124T065451Z/wsb_full")),
    ("rc5_per_experiments", Path("/data/yue2-runs/rc5-per-experiments")),
    ("rc5_q3o", Path("/data/yue2-runs/rc5-q3o")),
    ("rc5_evidence", Path("/data/yue2-runs/rc5-evidence")),
    ("rc5_restore_drill", Path("/data/yue2-runs/rc5-restore-drill")),
    ("backup_second_volume", Path("/workspace/yue2-rc5-backup/checkpoints")),
]

# Inside rc5_run_primary only identity-bearing files are frozen per-candidate
# (audio.flac, manifest.json); journal/run_config/evaluation_inputs are frozen
# whole. Large scratch (wavs staging) is skipped: it is rebuildable from the
# checkpoints.
PRIMARY_PER_CANDIDATE_FILES = ("audio.flac", "manifest.json", "result.json",
                               "config.json", "semantic.npy", "abc_tokens.npy",
                               "latent.npy", "prefix.npy", "plan.json",
                               "plan_manifest.json", "request.json", "score.abc")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_tree(name: str, root: Path):
    if not root.exists():
        return name, None, []
    if name == "rc5_run_primary":
        files = []
        for sub in sorted(root.rglob("*")):
            if not sub.is_file():
                continue
            rel = str(sub.relative_to(root))
            parts = rel.split("/")
            if parts and parts[0] == "songs" and len(parts) == 3:
                if parts[2] not in PRIMARY_PER_CANDIDATE_FILES:
                    continue
            if rel.startswith(("wavs/", "staging/")):
                continue
            files.append((rel, sub))
        return name, root, files
    if name == "rc5_5_reports":
        files = [(str(sub.relative_to(root)), sub) for sub in sorted(root.rglob("*"))
                 if sub.is_file() and "rc5_1" not in str(sub.relative_to(root))]
        return name, root, files
    files = [(str(sub.relative_to(root)), sub) for sub in sorted(root.rglob("*")) if sub.is_file()]
    return name, root, files


def build_freeze() -> dict:
    trees, total_files, total_bytes = {}, 0, 0
    for name, root in EVIDENCE_TREES:
        _, rootp, files = iter_tree(name, Path(root))
        if rootp is None:
            trees[name] = {"present": False, "files": 0, "bytes": 0, "sha256": None,
                           "entries": {}}
            continue
        entries = {}
        for rel, p in files:
            entries[rel] = sha256_file(p)
        nb = sum(p.stat().st_size for _, p in files)
        trees[name] = {"present": True, "root": str(rootp), "files": len(entries),
                       "bytes": nb, "entries": entries}
        total_files += len(entries)
        total_bytes += nb
        print(f"[freeze] {name}: {len(entries)} files, {nb/1e9:.2f} GB", file=sys.stderr)
    return {
        "schema": "yue2-rc6-evidence-freeze/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "protection": "RC6 work must not modify, delete or re-identify any frozen tree; "
                      "new experiments use independent run_ids and directories",
        "trees": trees,
        "total_files": total_files,
        "total_bytes": total_bytes,
    }


def verify_freeze(prev: dict) -> int:
    bad = 0
    for name, t in prev["trees"].items():
        _, rootp, files = iter_tree(name, Path(t.get("root", "")) if t.get("root") else
                                    dict(EVIDENCE_TREES)[name])
        if not t.get("present"):
            continue
        if rootp is None or not rootp.exists():
            print(f"[verify] {name}: TREE ABSENT")
            bad += 1
            continue
        cur = {rel: p for rel, p in files}
        for rel, want in t["entries"].items():
            p = cur.get(rel)
            if p is None:
                print(f"[verify] {name}/{rel}: MISSING")
                bad += 1
                continue
            got = sha256_file(p)
            if got != want:
                print(f"[verify] {name}/{rel}: HASH CHANGED")
                bad += 1
        for rel in cur:
            if rel not in t["entries"]:
                print(f"[verify] {name}/{rel}: EXTRA FILE (informational)")
    print(json.dumps({"verified": True, "mismatches": bad,
                      "trees": {k: v["files"] for k, v in prev["trees"].items()}}))
    return 0 if bad == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--verify", type=Path)
    a = ap.parse_args()
    if a.verify:
        return verify_freeze(json.loads(a.verify.read_text()))
    if not a.out:
        ap.error("--out or --verify required")
    freeze = build_freeze()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(freeze, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"frozen": freeze["total_files"], "bytes": freeze["total_bytes"],
                      "out": str(a.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
