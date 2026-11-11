#!/usr/bin/env python3
"""fetch_eval_assets_hub.py — fetch pinned WSB evaluator assets via huggingface_hub.

Why: the evaluator's own downloader (mot_infer.eval_assets.download) uses raw
urllib, which this host's egress proxy rejects with 503 on large CDN files.
huggingface_hub (requests-based, with resume/retry) is the proven path here
(it downloaded the 7.3 GB YuE2-3B snapshot through the same proxy).

The tool replicates the evaluator's download contract EXACTLY:
  * same pinned inventory rows (repo_id, revision, filename, sha256, bytes)
  * files land at the evaluator's expected paths
  * every file is sha256/size verified against the pin; mismatch aborts
It never touches evaluator code. Run `wsb_eval.py prepare` (without
--download) afterwards; verify_assets() sees a complete pinned tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

WSB = Path("/data/yue2/benchmark/WildSongBench")
sys.path.insert(0, str(WSB / "wsb_metrics"))
sys.path.insert(0, str(WSB / "wsb_metrics" / "src"))

from mot_infer.eval_assets import asset_rows, verify  # noqa: E402


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=WSB / "wsb_metrics")
    ap.add_argument("--metrics", default="per,songbench,mulan,allmusiccaps")
    ap.add_argument("--cache", type=Path, default=Path("/data/yue2/hf-cache"))
    args = ap.parse_args()
    metrics = [m for m in args.metrics.split(",") if m]
    rows = asset_rows(args.root, metrics)
    # group by repo to snapshot once per repo
    repos = {}
    for row in rows:
        if "repo_id" in row:
            repos.setdefault((row["repo_id"], row["revision"]), []).append(row)
    from huggingface_hub import snapshot_download
    for (repo_id, revision), rrows in sorted(repos.items()):
        rt = "dataset" if row_is_dataset(repo_id) else "model"
        print(f"snapshot {repo_id} @ {revision[:8]} ({len(rrows)} pinned files)", flush=True)
        snap = snapshot_download(repo_id=repo_id, revision=revision, repo_type=rt,
                                 cache_dir=str(args.cache),
                                 endpoint="https://hf-mirror.com",
                                 max_workers=4)
        snap = Path(snap)
        for row in rrows:
            src = snap / row["filename"]
            dst = args.root / row["path"]
            if dst.is_file() and dst.stat().st_size == row["bytes"] and sha256_of(dst) == row["sha256"]:
                continue
            if not src.is_file():
                print(f"FATAL: {row['filename']} missing from snapshot", flush=True)
                return 1
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            got = sha256_of(dst)
            ok = got == row["sha256"] and dst.stat().st_size == row["bytes"]
            print(f"{'OK  ' if ok else 'FAIL'} {row['path']} {got[:16]}", flush=True)
            if not ok:
                return 1
    # content-defined rows (small text assets bundled by the release)
    for row in rows:
        if "content" in row and not (args.root / row["path"]).is_file():
            p = args.root / row["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(row["content"])
    result = verify(args.root, metrics, force=True)
    print(json.dumps(result, indent=1)[:800])
    return 0 if not result["errors"] else 1


def row_is_dataset(repo_id: str) -> bool:
    return False


if __name__ == "__main__":
    raise SystemExit(main())
