#!/usr/bin/env python3
"""verify_transfer_bundle.py — fail-closed receiving-side check for the RC2
CUDA handoff bundle (validated procedure; see README_CUDA_RUNBOOK.md).

Verifies, WITHOUT any GPU or evaluator install:
  * every expected candidate directory exists;
  * every file matches the manifest's sha256 + byte size;
  * the official checker's required artifact set is present per candidate;
  * evaluation_inputs.jsonl row count == manifest count == 384 (standard mode);
  * candidate ids match the strict on-disk naming contract (no path
    traversal via crafted manifest ids);
  * no symlink anywhere in the verified tree (a regular file whose CONTENT
    hash matches but which points OUTSIDE the bundle — e.g. at the sender's
    original campaign tree — must be rejected: the bundle must be
    self-contained, and the receiving side must never be tricked into
    reading files outside what was actually transferred);
  * evaluation_inputs.jsonl "path" fields are exactly "songs/<id>" (relative,
    no "..", consistent with the manifest row they correspond to).

Exit 0 only on a fully-verified bundle. First mismatch aborts with a
precise, actionable message (transfer-corruption diagnosis, not a stack dump).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REQUIRED = {"audio.flac", "prefix.npy", "semantic.npy", "latent.npy",
            "request.json", "config.json", "result.json"}

ID_RE = re.compile(r"wsb_(\d{3})_r([01])_s(\d{6})\Z")


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
    if inputs.is_symlink() or not inputs.is_file():
        return fail(f"missing (or symlinked) {inputs}")
    rows = [json.loads(l) for l in inputs.read_text().splitlines() if l.strip()]
    if len(rows) != 384:
        return fail(f"evaluation_inputs.jsonl has {len(rows)} rows (expected 384)")
    if (a.bundle / "songs").is_symlink():
        return fail("songs/ is a symlink (bundle must be self-contained)")

    # strict id/path contract, checked BEFORE any filesystem use of the id:
    # a crafted manifest id like "../../etc" must never escape the bundle
    seen_ids = set()
    for e in entries:
        cid = e.get("id")
        if not isinstance(cid, str) or not ID_RE.fullmatch(cid):
            return fail(f"manifest id {cid!r} violates the candidate naming contract")
        if cid in seen_ids:
            return fail(f"duplicate manifest id {cid}")
        seen_ids.add(cid)
        i, j = int(ID_RE.fullmatch(cid).group(1)), int(ID_RE.fullmatch(cid).group(2))
        if e.get("prompt_index") != i or e.get("candidate_index") != j:
            return fail(f"{cid}: manifest index fields disagree with the id")
    valid_paths = {f"songs/{c}" for c in seen_ids}
    for row in rows:
        path = row.get("path")
        if not isinstance(path, str) or path not in valid_paths:
            return fail(f"evaluation_inputs path {path!r} is not 'songs/<manifest id>' "
                        "(absolute or traversing paths are rejected)")

    n_files = 0
    for e in entries:
        d = a.bundle / "songs" / e["id"]
        if d.is_symlink() or not d.is_dir():
            return fail(f"missing candidate dir songs/{e['id']} "
                        "(or it is a symlink)")
        missing = REQUIRED - set(e["files"])
        if missing:
            return fail(f"{e['id']}: manifest lacks required {sorted(missing)}")
        for name, meta in e["files"].items():
            if name != Path(name).name or name in {"", ".", ".."}:
                return fail(f"{e['id']}: invalid file name in manifest {name!r}")
            p = d / name
            if p.is_symlink():
                return fail(f"{e['id']}/{name}: symlink rejected "
                            "(bundle must be self-contained; re-send the real file)")
            if not p.is_file():
                return fail(f"{e['id']}/{name}: file missing")
            if p.stat().st_size != meta["bytes"]:
                return fail(f"{e['id']}/{name}: size {p.stat().st_size} != "
                            f"{meta['bytes']} (truncated transfer?)")
            if sha256(p) != meta["sha256"]:
                return fail(f"{e['id']}/{name}: sha256 mismatch (corrupted)")
            n_files += 1
    print(f"bundle OK: {len(entries)} candidates, {n_files} files verified "
          f"(all sha256 + sizes match; required artifact set present; "
          f"no symlinks; ids and paths within contract)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
