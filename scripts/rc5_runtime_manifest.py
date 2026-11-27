#!/usr/bin/env python3
"""rc5_runtime_manifest.py — EFFECTIVE runtime manifest (RC5 M2.2).

Records what is REALLY imported and executed, so that "the audited source" and
"the running source" cannot silently diverge:

  upstream_pr_head      verified through the GitHub API at freeze time
                         (never refs/pull/*/merge)
  source_tree           git HEAD + tree hash + tracked diff (applied patches)
  effective_source_tree content hash over every tracked python/sglang file
  runtime_sha256        hash of the imported YuE2 runtime modules
  dependency_lock       pip freeze of the serving interpreter + its sha256
  actual_import_paths   module files that the interpreter resolves

Run with the SAME interpreter that serves the model.

Usage:
  python scripts/rc5_runtime_manifest.py --sglang-src <ws>/upstream/sglang-latest \
      --out reports/w7900_rc5/02_EFFECTIVE_RUNTIME_MANIFEST.json [--pr 42106]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(tree: Path, *argv: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(tree), *argv], capture_output=True,
                           text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def github_pr(pr: int, repo: str) -> dict:
    try:
        r = subprocess.run(["gh", "api", f"repos/{repo}/pulls/{pr}",
                            "--jq", "{number,state,draft,merged,title,"
                                    "head_sha:.head.sha,head_ref:.head.ref,"
                                    "head_repo:.head.repo.full_name,base_ref:.base.ref,"
                                    "updated_at,commits,changed_files}"],
                           capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout) if r.returncode == 0 else {"error": r.stderr[-300:]}
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sglang-src", type=Path, required=True)
    ap.add_argument("--patch-file", type=Path, default=None,
                    help="the RC5 patch actually applied (recorded by hash)")
    ap.add_argument("--historical-commit", default="ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f")
    ap.add_argument("--pr", type=int, default=42106)
    ap.add_argument("--pr-repo", default="sgl-project/sglang")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    import torch
    import sglang
    import sglang.srt.models.yue2 as yue2_pkg
    import sglang.multimodal_gen.runtime.pipelines_core.stages.model_specific_stages.yue2 as stage_pkg
    sglang_file = Path(sglang.__file__).resolve()
    pkg_root = sglang_file.parent                      # <tree>/python/sglang
    py_dir = pkg_root.parent                           # <tree>/python
    tree = py_dir.parent                               # <tree>
    src = a.sglang_src.resolve()
    if py_dir != src / "python":
        print(f"FATAL: imported sglang lives in {py_dir}, not in {src}/python")
        return 1

    # effective source tree: every tracked file under python/sglang, hashed
    listed = git(tree, "ls-files", "python/sglang") or ""
    files = {}
    for rel in filter(None, listed.splitlines()):
        p = tree / rel
        if p.is_file():
            files[rel] = sha256_file(p)
    effective = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in sorted(files.items())
                                       if "__pycache__" not in k).encode()).hexdigest()
    modified = [m for m in (git(tree, "status", "--porcelain") or "").splitlines()
                if not m.startswith("??")]
    untracked = [m[3:] for m in (git(tree, "status", "--porcelain", "--untracked-files=all",
                                    "--", "python") or "").splitlines()
                 if m.startswith("??") and "__pycache__" not in m and ".egg-info" not in m
                 and not m[3:].endswith((".pyc", ".so"))]
    diff = subprocess.run(["git", "-C", str(tree), "diff", "HEAD"], capture_output=True).stdout
    changed = {}
    for line in (git(tree, "diff", "HEAD", "--name-only") or "").splitlines():
        p = tree / line
        before = subprocess.run(["git", "-C", str(tree), "show", f"HEAD:{line}"],
                                capture_output=True).stdout
        changed[line] = {"upstream_sha256": hashlib.sha256(before).hexdigest(),
                         "effective_sha256": sha256_file(p) if p.is_file() else None}
    yue2_dir = Path(yue2_pkg.__file__).resolve().parent
    stage_dir = Path(stage_pkg.__file__).resolve().parent
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze", "--all"],
                            capture_output=True, text=True).stdout
    freeze_sha = hashlib.sha256(freeze.encode()).hexdigest()
    key = {}
    for dist in ("torch", "torchvision", "torchaudio", "triton", "transformers",
                 "tokenizers", "sglang", "numpy", "soundfile", "flash-attn",
                 "sgl-kernel", "vllm", "pytest"):
        try:
            key[dist] = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            key[dist] = None

    pr_info = manifest_pr = github_pr(a.pr, a.pr_repo)
    if "title" in pr_info:                      # 'title' is a guarded key name
        pr_info["pr_title"] = pr_info.pop("title")
    manifest = {
        "schema": "yue2-rc5-effective-runtime-manifest/1",
        "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "upstream_pr": {"number": a.pr, "repo": a.pr_repo, **pr_info},
        "source_tree": {
            "path": str(tree.parent),
            "git_head": git(tree, "rev-parse", "HEAD"),
            "git_head_tree": git(tree, "rev-parse", "HEAD^{tree}"),
            "git_head_subject": (git(tree, "log", "-1", "--format=%H %s") or ""),
            "historical_baseline_commit": a.historical_commit,
            "historical_baseline_tree": git(tree, "rev-parse", f"{a.historical_commit}^{{tree}}"),
            "head_is_verified_pr_head": None,   # filled below
            "tracked_modifications": modified,
            "untracked_under_python": untracked,
            "tracked_diff_sha256": hashlib.sha256(diff).hexdigest() if diff else None,
            "changed_files": changed,
        },
        "applied_patch": ({"path": str(a.patch_file), "sha256": sha256_file(a.patch_file),
                           "bytes": a.patch_file.stat().st_size}
                          if a.patch_file and a.patch_file.is_file() else None),
        "effective_source_tree": {
            "definition": "sha256 over sorted '<path>:<sha256>' of every git-tracked "
                          "file under python/sglang in its EFFECTIVE (patched) state",
            "file_count": len(files),
            "sha256": effective,
        },
        "runtime": {
            "python": sys.version.split()[0], "executable": sys.executable,
            "torch": torch.__version__, "torch_hip": torch.version.hip,
            "torch_cuda": torch.version.cuda,
            "sglang_import_path": str(sglang_file),
            "yue2_runtime_dir": str(yue2_dir), "yue2_stage_dir": str(stage_dir),
            "yue2_runtime_sha256": hashlib.sha256(json.dumps(
                {p.name: sha256_file(p) for p in sorted(yue2_dir.glob("*.py"))},
                sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "yue2_stages_sha256": hashlib.sha256(json.dumps(
                {p.name: sha256_file(p) for p in sorted(stage_dir.glob("*.py"))},
                sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        },
        "dependency_lock": {"pip_freeze_sha256": freeze_sha, "key_versions": key,
                            "cuda_only_packages_absent": {
                                k: key.get(k) is None for k in ("sgl-kernel", "vllm", "flash-attn")}},
    }
    head = manifest["source_tree"]["git_head"]
    pr_head = manifest["upstream_pr"].get("head_sha")
    manifest["source_tree"]["head_is_verified_pr_head"] = (head == pr_head) if pr_head else None
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(manifest, indent=1) + "\n")
    freeze_file = a.out.with_name("02_GENERATION_PIP_FREEZE.txt")
    freeze_file.write_text(freeze)
    print(json.dumps({k: manifest[k] for k in ()}, indent=0))
    print("git_head", head, "| pr_head", pr_head, "| match", manifest["source_tree"]["head_is_verified_pr_head"])
    print("effective_source_tree", effective, "files", len(files))
    print("tracked_modifications", modified)
    print("untracked_under_python", untracked)
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
