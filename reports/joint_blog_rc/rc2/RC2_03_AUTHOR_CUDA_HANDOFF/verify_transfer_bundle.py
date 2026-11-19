#!/usr/bin/env python3
"""verify_transfer_bundle.py — fail-closed receiving-side check for the RC2
CUDA handoff bundle (validated procedure; see README_CUDA_RUNBOOK.md).

Verifies, WITHOUT any GPU or evaluator install:
  * every expected candidate directory exists;
  * every file matches the manifest's sha256 + byte size;
  * the official checker's required artifact set is present per candidate;
  * evaluation_inputs.jsonl row count == manifest count == 384 (standard mode).

Exit 0 only on a fully-verified bundle. First mismatch aborts with a
precise, actionable message (transfer-corruption diagnosis, not a stack dump).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REQUIRED = {"audio.flac", "prefix.npy", "semantic.npy", "latent.npy",
            "request.json", "config.json", "result.json"}


def fail(msg: str) -> int:
    print(f"BUNDLE VERIFY FAIL: {msg}")
    return 1


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, required=True,
                    help="directory containing evaluation_inputs.jsonl + songs/")
    ap.add_argument("--manifest", type=Path, required=True,
                    help="armX_bundle_manifest.json from the transfer")
    a = ap.parse_args()

    m = json.loads(a.manifest.read_text())
    if m.get("schema") != "rc2-cuda-transfer-bundle/v2":
        return fail(f"unexpected manifest schema {m.get('schema')!r}")
    entries = m["files"]
    if len(entries) != 384:
        return fail(f"manifest lists {len(entries)} candidates (expected 384)")

    inputs = a.bundle / "evaluation_inputs.jsonl"
    if not inputs.is_file():
        return fail(f"missing {inputs}")
    rows = [json.loads(l) for l in inputs.read_text().splitlines() if l.strip()]
    if len(rows) != 384:
        return fail(f"evaluation_inputs.jsonl has {len(rows)} rows (expected 384)")

    n_files = 0
    for e in entries:
        d = a.bundle / "songs" / e["id"]
        if not d.is_dir():
            return fail(f"missing candidate dir songs/{e['id']}")
        missing = REQUIRED - set(e["files"])
        if missing:
            return fail(f"{e['id']}: manifest lacks required {sorted(missing)}")
        for name, meta in e["files"].items():
            p = d / name
            if not p.is_file():
                return fail(f"{e['id']}/{name}: file missing")
            if p.stat().st_size != meta["bytes"]:
                return fail(f"{e['id']}/{name}: size {p.stat().st_size} != "
                            f"{meta['bytes']} (truncated transfer?)")
            if sha256(p) != meta["sha256"]:
                return fail(f"{e['id']}/{name}: sha256 mismatch (corrupted)")
            n_files += 1
    print(f"bundle OK: {len(entries)} candidates, {n_files} files verified "
          f"(all sha256 + sizes match; required artifact set present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
