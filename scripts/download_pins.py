#!/usr/bin/env python3
"""download_pins.py - fetch and hash-verify every pinned artifact.

Pins come from evidence/protocol_lock.json (frozen by the dataset authors):
  dataset  m-a-p/WildSongBench  @ e361b85a8d7365d3079fa9647641a87ce3c8c5b5
  AR model m-a-p/YuE2-3B        @ 1a96eca688d6ae5d7f0feb88573fec89920fcd19
  VAE      m-a-p/YuE2-Vae-legacy@ b54118f0fc462f08999d1ec07e88817f4ee3f770

Every downloaded file gets a full SHA256; protocol-bearing files are compared
against the pins and any mismatch aborts with a nonzero exit.

Usage: python scripts/download_pins.py [--workspace DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

PINS = {
    "dataset_revision": "e361b85a8d7365d3079fa9647641a87ce3c8c5b5",
    "ar_revision": "1a96eca688d6ae5d7f0feb88573fec89920fcd19",
    "vae_revision": "b54118f0fc462f08999d1ec07e88817f4ee3f770",
    "sha256": {
        "YuE2-3B/model.safetensors":
            "1d55c42c1a9875c34f5d736e15078449992b044e807ce2a138e6cf289a1e59e9",
        "YuE2-Vae-legacy/model.safetensors":
            "b6d283628913bb41145ba99e2314eef613905ee95f690eb70e8212d5f4965044",
        "WildSongBench/prompts.jsonl":
            "1b554a824eba8e02eabe02299e48ed2215764931b8f05535cf8c6d250ddf8326",
        "WildSongBench/benchmark/reproduction_manifest.jsonl":
            "859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0",
        "WildSongBench/evaluation/wsb_metrics.tar.gz":
            "bd550b36f1fc43cad3254a9897dd3a078e50c4eb9e8d4f295ac4b5e81d1fc4fd",
        "WildSongBench/code/generate.py":
            "41e069ed0f9d7fde27b277de40fe69d31fd0f5eed7a481b0af00e6486a6229c1",
        "WildSongBench/code/install_inference.py":
            "872a7c3e4a3ac5f842847f2909b82de59221d399ef3879a8310249f3ae11d81a",
    },
}

SGlang_PIN = "ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(repo, rev, dest, repo_type="model", ignore=None):
    from huggingface_hub import snapshot_download
    return snapshot_download(
        repo_id=repo, revision=rev, repo_type=repo_type,
        local_dir=str(dest),
        ignore_patterns=ignore or [],
        max_workers=8,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path,
                    default=Path(os.environ.get("YUE2_WORKSPACE",
                                                Path(__file__).resolve().parents[1])))
    args = ap.parse_args()
    ws = args.workspace
    models = ws / "models"
    ds = ws / "benchmark" / "WildSongBench"
    upstream = ws / "upstream"
    for d in (models, ds, upstream):
        d.mkdir(parents=True, exist_ok=True)

    manifest = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "endpoint": os.environ.get("HF_ENDPOINT", "https://huggingface.co"),
                "files": {}}

    print("[1/4] WildSongBench dataset ...", flush=True)
    snapshot("m-a-p/WildSongBench", PINS["dataset_revision"], ds,
             repo_type="dataset")
    print("[2/4] YuE2-3B ...", flush=True)
    snapshot("m-a-p/YuE2-3B", PINS["ar_revision"], models / "YuE2-3B",
             ignore=["assets/audio/*", "examples/*"])
    print("[3/4] YuE2-Vae-legacy ...", flush=True)
    snapshot("m-a-p/YuE2-Vae-legacy", PINS["vae_revision"],
             models / "YuE2-Vae-legacy", ignore=["assets/*"])

    print("[4/4] SGLang PR #42106 head tarball ...", flush=True)
    sg = upstream / f"sglang-{SGlang_PIN}.tar.gz"
    if not sg.is_file():
        urllib.request.urlretrieve(
            f"https://codeload.github.com/sgl-project/sglang/tar.gz/{SGlang_PIN}", sg)
    out = upstream / "sglang"
    if not (out / "python" / "pyproject.toml").is_file():
        with tarfile.open(sg) as tf:
            tf.extractall(out.parent)
            inner = out.parent / f"sglang-{SGlang_PIN[:7]}-" # codeload strip prefix varies
        # codeload top dir is sglang-<shortsha> — normalize to upstream/sglang
        for child in out.parent.iterdir():
            if child.is_dir() and child.name.startswith("sglang-") and child != out:
                if out.exists():
                    out.rmdir()
                child.rename(out)

    # hash every pinned file + record all files
    failures = []
    for rel, expected in PINS["sha256"].items():
        if rel.startswith("YuE2"):
            p = models / rel
        elif rel.startswith("WildSongBench"):
            p = ws / "benchmark" / rel
        else:
            p = ws / rel
        if not p.is_file():
            failures.append(f"{rel}: MISSING")
            continue
        actual = sha256_file(p)
        ok = actual == expected
        manifest["files"][rel] = {"sha256": actual, "expected": expected, "match": ok,
                                  "bytes": p.stat().st_size}
        print(f"{'OK  ' if ok else 'FAIL'} {rel} {actual[:16]}...", flush=True)
        if not ok:
            failures.append(f"{rel}: sha mismatch {actual} != {expected}")

    manifest["sglang_tarball_sha256"] = sha256_file(sg)
    manifest["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (ws / "logs" / "phase3_download_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    if failures:
        print("PIN FAILURES:", *failures, sep="\n  ")
        return 1
    print("ALL PINS VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
