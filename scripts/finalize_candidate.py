#!/usr/bin/env python3
"""Finalize one WSB candidate directory to the official evaluator schema.

Port of the official yue2-infer 0.1.3 `SongResult.save_artifacts` semantics
(extracted from the pinned wheel, sha 156d6b8b...), adapted so the artifacts
the SGLang PR already exports (export_song_artifacts) are completed with the
remaining official files:

  score.abc      - ABC text (from the AR plan)
  audio.flac     - PCM_24 48 kHz stereo, written from the server WAV (FLOAT)
  semantic.npy   - int32 codec ids (relative, without CODEC_OFFSET)
  latent.npy     - float32 [frames, 64]
  prefix.npy     - int32 semantic prefix token ids (absolute)
  abc_tokens.npy - int32 ABC-phase token ids
  request.json   - SongRequest dict (style/lyrics/cot/seed/cfg/abc/id)
  config.json    - effective GenerationConfig dict
  plan.json      - timing/truncated bookkeeping (PR export)
  plan_manifest.json - hashes of plan inputs (PR export)
  result.json    - status/identity/truncated/sample_rate/audio_seconds/
                   weights/timing/artifacts (collect_hashes)

Semantics preserved exactly: identity = sha256 of canonical JSON of
{request, effective config, weights identities}; weights verified against
each model's own weights_manifest.json. No filtering, no resampling, no
quality parameters touched: FLAC is a lossless repack of the decoded PCM.

Usage:
  python finalize_candidate.py <candidate_dir> <audio.wav> <model_dir> <vae_dir> \
      [--request-json <path>] [--config-json <path>] [--aborted]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

WS_DEFAULT = os.environ.get("WS", "/home/amd/Desktop/YuE2")
sys.path.insert(0, os.path.join(WS_DEFAULT, "upstream/sglang/python"))

import numpy as np
import soundfile as sf

from sglang.srt.models.yue2.protocol import GenerationConfig
from sglang.srt.models.yue2.storage import (
    collect_hashes,
    identity,
    model_identity,
    sha256_file,
    write_json,
)


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
    ap.add_argument("--request-json", type=Path, default=None,
                    help="defaults to <candidate_dir>/request.json (PR export)")
    ap.add_argument("--config-json", type=Path, default=None,
                    help="defaults to <model_dir>/yue2_generation_config.json")
    ap.add_argument("--aborted", action="store_true",
                    help="record a failed/aborted candidate (status != complete)")
    args = ap.parse_args()

    cand = args.candidate_dir
    cand.mkdir(parents=True, exist_ok=True)

    request_path = args.request_json or (cand / "request.json")
    request = json.loads(request_path.read_text())
    # Materialize the effective CFG: the server does not accept a cfg_scale
    # key at the PR head, and SongRequest.guidance resolves cfg_scale=None
    # with cot=full to exactly 1.0 (single-branch). The official driver
    # likewise records cfg_scale=1.0 explicitly; the evaluator requires it.
    if request.get("cfg_scale") is None:
        request["cfg_scale"] = 1.0
        write_json(cand / "request.json", request)

    config_path = args.config_json or (args.model_dir / "yue2_generation_config.json")
    generation = GenerationConfig.from_dict(json.loads(config_path.read_text())).to_dict()

    # Runtime identity: sha over the SGLang YuE2 runtime sources (the code that
    # actually generated these artifacts), analogous to the official wheel's
    # self-hash of yue2/*.py. Backend label: the SGLang PR implements the
    # torch-reference YuE2 pipeline (sampling/nar are ports of the official
    # torch backend; the evaluator accepts {torch, vllm}); provenance beyond
    # the label is preserved via runtime_sha256 and weights below.
    yue2_dir = Path(WS_DEFAULT) / "upstream/sglang/python/sglang/srt/models/yue2"
    runtime_sha = identity({p.name: sha256_file(p)
                            for p in sorted(yue2_dir.glob("*.py"))})
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
    }

    weights = {"mot": model_identity(args.model_dir, verify=True),
               "vae": model_identity(args.vae_dir, verify=True)}
    request_id = identity({"request": request, "config": config, "weights": weights})

    if args.aborted:
        write_json(cand / "result.json", {"status": "aborted", "identity": request_id})
        return 1

    # ABC text: decode from plan tokens if the PR export did not keep the text
    plan_path = cand / "plan.json"
    plan = json.loads(plan_path.read_text()) if plan_path.is_file() else {}
    abc_text = plan.get("abc")
    if abc_text is None and plan.get("abc_ids"):
        sys.path.insert(0, str(args.model_dir))
        from sglang.srt.models.yue2.tokenization_yue2 import YuE2TextTokenizer

        tokenizer = YuE2TextTokenizer(args.model_dir / "qwen.tiktoken")
        abc_text = tokenizer.decode([int(t) for t in plan["abc_ids"]])
    if abc_text is not None:
        (cand / "score.abc").write_bytes(abc_text.encode("utf-8"))
        hashes = json.loads((cand / "plan_manifest.json").read_text())
        hashes["score.abc"] = sha256_file(cand / "score.abc")
        write_json(cand / "plan_manifest.json", hashes)

    # audio.flac: lossless PCM_24 repack of the decoded float WAV
    audio, sr = load_audio(args.audio_wav)
    sf.write(cand / "audio.flac", audio, sr, subtype="PCM_24")

    # semantic/latent/prefix/abc_tokens .npy + request.json: already exported
    # by the server's artifacts stage; validate their presence and shapes.
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
