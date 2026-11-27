#!/usr/bin/env python3
"""rc5_download_q3o.py — fetch the OFFICIAL Q3O judge checkpoint and verify
every file against the evaluator's own asset manifest (RC5 M7.1/M7.2).

The model identity comes from the frozen evaluator bundle, not from a name in
a report: configs/evaluation_assets.json pins repo_id, revision, byte size and
SHA256 of every file. Nothing is trusted unless all four match.

Usage:
  python scripts/rc5_download_q3o.py --evaluator-root <ws>/benchmark/WildSongBench/wsb_metrics \
      --dest <ws>/models/Qwen3-Omni-30B-A3B-Instruct [--manifest out.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator-root", type=Path, required=True)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--metric", default="q3o")
    ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()

    assets = json.loads((a.evaluator_root / "configs/evaluation_assets.json").read_text())
    spec = assets["models"][a.metric]
    files = [f for f in assets["files"] if f.get("repo_id") == spec["repo_id"]
             and f.get("revision") == spec["revision"]
             and a.metric in f.get("metrics", [])]
    print(json.dumps({k: spec[k] for k in ("repo_id", "revision")}))
    print(f"{len(files)} pinned files, {sum(f['bytes'] for f in files)/1e9:.2f} GB")

    if not a.verify_only:
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from huggingface_hub import snapshot_download
        t0 = time.time()
        for attempt in range(1, 21):
            try:
                snapshot_download(repo_id=spec["repo_id"], revision=spec["revision"],
                                  local_dir=str(a.dest),
                                  allow_patterns=[f["filename"] for f in files]
                                  + ["model-?????-of-?????.safetensors"],
                                  max_workers=8)
                break
            except Exception as e:  # noqa: BLE001 - resume is the point
                print(f"[attempt {attempt}] {type(e).__name__}: {e}", flush=True)
                time.sleep(min(60, 5 * attempt))
        else:
            print("DOWNLOAD FAILED after 20 attempts")
            return 1
        print(f"download finished in {time.time()-t0:.0f}s")

    manifest = {"repo_id": spec["repo_id"], "revision": spec["revision"],
                "dest": str(a.dest), "files": {}, "ok": True}
    for f in sorted(files, key=lambda x: x["filename"]):
        p = a.dest / f["filename"]
        rec = {"bytes": f["bytes"], "sha256_expected": f["sha256"]}
        if not p.is_file():
            rec.update(status="MISSING")
            manifest["ok"] = False
        else:
            size_ok = p.stat().st_size == f["bytes"]
            digest = sha256_file(p)
            rec.update(bytes_actual=p.stat().st_size, sha256_actual=digest,
                       status="OK" if (size_ok and digest == f["sha256"]) else "MISMATCH")
            if rec["status"] != "OK":
                manifest["ok"] = False
        manifest["files"][f["filename"]] = rec
        print(f"{rec['status']:8s} {f['filename']}", flush=True)
    if a.manifest:
        a.manifest.parent.mkdir(parents=True, exist_ok=True)
        a.manifest.write_text(json.dumps(manifest, indent=1) + "\n")
    print("ALL Q3O FILES VERIFIED" if manifest["ok"] else "Q3O VERIFICATION FAILED")
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
