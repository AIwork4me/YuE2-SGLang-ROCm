#!/usr/bin/env python3
"""finalize_candidate_omni.py - finalize an Omni-served WSB candidate bundle.

Identical semantics to evidence-repo finalize_candidate.py (official yue2-infer
0.1.3 SongResult.save_artifacts port) with exactly two arm-B differences:

  1. runtime_sha256 hashes the SGLang-Omni YuE2 runtime sources
     (sglang_omni/models/yue2/*.py) - the code that actually generated the
     artifacts - instead of the original SGLang tree.
  2. serving_stack records the Omni provenance fields for the report.

The server (bench-only instrumentation, omni commit c4841f0c) exports
plan.json, plan_manifest.json, request.json, semantic.npy, latent.npy,
prefix.npy, abc_tokens.npy via export_song_artifacts; this script completes
audio.flac, config.json, result.json exactly like the arm-A finalizer.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

WS = Path(os.environ.get("YUE2_WORKSPACE", "/workspace/yue2-sglang-rocm-w7900"))
sys.path.insert(0, "/workspace/yue2-omni-pr/repo")

import numpy as np
import soundfile as sf

from sglang_omni.models.yue2.protocol import GenerationConfig
from sglang_omni.models.yue2.storage import (
    collect_hashes,
    identity,
    model_identity,
    sha256_file,
    write_json,
)

OMNI_YUE2_DIR = Path("/workspace/yue2-omni-pr/repo/sglang_omni/models/yue2")


def load_audio(wav: Path):
    audio, sr = sf.read(wav, dtype="float64", always_2d=True)
    if sr != 48000:
        raise ValueError(f"expected 48 kHz audio, got {sr}")
    audio = np.clip(audio, -1.0, 1.0)
    return audio, sr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate_dir", type=Path)
    ap.add_argument("audio_wav", type=Path)
    ap.add_argument("model_dir", type=Path)
    ap.add_argument("vae_dir", type=Path)
    ap.add_argument("--request-json", type=Path, default=None)
    ap.add_argument("--config-json", type=Path, default=None)
    ap.add_argument("--aborted", action="store_true")
    args = ap.parse_args()

    cand = args.candidate_dir
    cand.mkdir(parents=True, exist_ok=True)

    request_path = args.request_json or (cand / "request.json")
    request = json.loads(request_path.read_text())
    if request.get("cfg_scale") is None:
        request["cfg_scale"] = 1.0
        write_json(cand / "request.json", request)

    config_path = args.config_json or (args.model_dir / "yue2_generation_config.json")
    generation = GenerationConfig.from_dict(json.loads(config_path.read_text())).to_dict()

    runtime_sha = identity({p.name: sha256_file(p)
                            for p in sorted(OMNI_YUE2_DIR.glob("*.py"))})
    config = {
        "generation": generation, "overrides": {},
        "cot": request.get("cot", "full"), "cfg_scale": request.get("cfg_scale", 1.0),
        "cfg_negative": None, "backend": "torch",
        "quantization": "none", "model_dtype": "bfloat16", "vae_dtype": "float32",
        "vae_decode": "halo_crop",
        "vae_core_frames": int(request.get("_vae_core_frames", 0) or 1024),
        "vae_halo_frames": int(request.get("_vae_halo_frames", 0) or 16),
        "runtime_sha256": runtime_sha,
        "memory_budget_gib": None, "offload_ar": False,
        "serving_stack": "sglang-omni",
    }

    weights = {"mot": model_identity(args.model_dir, verify=True),
               "vae": model_identity(args.vae_dir, verify=True)}
    request_id = identity({"request": request, "config": config, "weights": weights})

    if args.aborted:
        write_json(cand / "result.json", {"status": "aborted", "identity": request_id})
        return 1

    plan_path = cand / "plan.json"
    plan = json.loads(plan_path.read_text()) if plan_path.is_file() else {}
    abc_text = plan.get("abc")
    if abc_text is None and plan.get("abc_ids"):
        sys.path.insert(0, str(args.model_dir))
        from sglang_omni.models.yue2.tokenization_yue2 import YuE2TextTokenizer

        tokenizer = YuE2TextTokenizer(args.model_dir / "qwen.tiktoken")
        abc_text = tokenizer.decode([int(t) for t in plan["abc_ids"]])
    if abc_text is not None:
        (cand / "score.abc").write_bytes(abc_text.encode("utf-8"))
        hashes = json.loads((cand / "plan_manifest.json").read_text())
        hashes["score.abc"] = sha256_file(cand / "score.abc")
        write_json(cand / "plan_manifest.json", hashes)

    audio, sr = load_audio(args.audio_wav)
    sf.write(cand / "audio.flac", audio, sr, subtype="PCM_24")

    write_json(cand / "config.json", config)
    sem = np.load(cand / "semantic.npy", allow_pickle=False)
    lat = np.load(cand / "latent.npy", allow_pickle=False)
    pre = np.load(cand / "prefix.npy", allow_pickle=False)
    if sem.ndim != 1 or sem.dtype != np.int32:
        raise ValueError("semantic.npy must be int32 1-D codec ids")
    if lat.shape != (len(sem), 64) or not np.isfinite(lat).all():
        raise ValueError(f"latent.npy shape {lat.shape} invalid for {len(sem)} frames")
    if pre.ndim != 1:
        raise ValueError("prefix.npy must be 1-D")

    truncated = bool(plan.get("truncated", False))
    timing = plan.get("timing", {})
    result = {
        "status": "complete",
        "identity": request_id,
        "truncated": truncated,
        "sample_rate": sr,
        "audio_seconds": len(audio) / sr,
        "weights": weights,
        "timing": timing,
        "artifacts": collect_hashes(cand),
    }
    write_json(cand / "result.json", result)
    print(json.dumps({"status": "complete", "identity": request_id,
                      "audio_seconds": result["audio_seconds"],
                      "truncated": truncated, "codec_frames": int(len(sem))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
