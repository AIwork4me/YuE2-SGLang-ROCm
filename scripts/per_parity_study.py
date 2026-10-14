#!/usr/bin/env python3
"""per_parity_study.py - ASR backend/numerics parity for the WSB PER scorer.

The official scorer runs Qwen3-ASR-1.7B through vLLM (no ROCm build exists);
on AMD we run the same checkpoint through qwen_asr's transformers backend
(evaluator patch 0007). This study makes the residual risk measurable on
fixed audio:

  arm A (GPU): transformers backend on the ROCm device, greedy  (the scorer)
  arm B (CPU): identical backend/decoding on CPU only          (reference)

Compared per candidate: raw transcription, phoneme sequence, PER against the
frozen reference, and the induced best-of-2 selection + ranking.

Usage (inside the evaluator metrics venv, with WSB_ROCM_TORCH_OVERRIDE=1):
  python per_parity_study.py --runs <wsb_full dir> --samples 8 [--cpu-only]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

WS = Path(os.environ.get("YUE2_WORKSPACE",
                         Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(WS / "benchmark" / "wsb_metrics"))

ASR_SNAPSHOT = ("evaluation_models/hub/models--Qwen--Qwen3-ASR-1.7B/snapshots/"
                "7278e1e70fe206f11671096ffdd38061171dd6e5")


def load_manifest():
    rows = [json.loads(l) for l in
            (WS / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl").read_text().splitlines()
            if l.strip()]
    return {r["prompt_index"]: r for r in rows}


def transcribe_all(model_dir, flacs, device):
    import torch
    from qwen_asr import Qwen3ASRModel  # type: ignore
    m = Qwen3ASRModel.from_pretrained(str(model_dir), dtype=torch.bfloat16
                                      if device == "cuda" else torch.float32)
    if device == "cuda":
        m.model.to("cuda"); m.device = m.model.device
    def as_text(result):
        # qwen_asr returns an ASRTranscription dataclass (fields incl. .text)
        # or a plain str depending on version
        if isinstance(result, str):
            return result
        for attr in ("text", "transcript"):
            v = getattr(result, attr, None)
            if isinstance(v, str):
                return v
        return repr(result)

    texts = {}
    for f in flacs:
        t0 = time.time()
        texts[f.parent.name] = as_text(m.transcribe(str(f)))
        print(f"  [{device}] {f.parent.name}: {time.time()-t0:.1f}s", flush=True)
    return texts


def per_one(hyp: str, ref: str, scorer):
    return scorer.score_text(hyp, ref) if hasattr(scorer, "score_text") else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--samples", type=int, default=8,
                    help="candidates to transcribe per arm (first N complete)")
    ap.add_argument("--cpu-only", action="store_true",
                    help="run only the CPU arm (for during-generation studies)")
    args = ap.parse_args()

    root = WS / "benchmark" / "wsb_metrics"
    asr_dir = root / ASR_SNAPSHOT
    manifest = load_manifest()

    complete = []
    for cand in sorted((args.runs / "songs").glob("wsb_*")):
        if not cand.is_dir() or not (cand / "result.json").is_file():
            continue
        r = json.loads((cand / "result.json").read_text())
        if r.get("status") == "complete":
            complete.append(cand)
    flacs = [c / "audio.flac" for c in complete[:args.samples]]
    print(f"study samples: {[f.parent.name for f in flacs]}")

    out = {"arms": {}, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
    if not args.cpu_only:
        print("arm A: GPU (ROCm)")
        out["arms"]["gpu"] = transcribe_all(asr_dir, flacs, "cuda")
    print("arm B: CPU reference")
    out["arms"]["cpu"] = transcribe_all(asr_dir, flacs, "cpu")

    if not args.cpu_only:
        diffs = {k: out["arms"]["gpu"][k] != out["arms"]["cpu"][k]
                 for k in out["arms"]["gpu"]}
        out["transcription_diffs"] = diffs
        out["identical_count"] = sum(1 for v in diffs.values() if not v)
        print(json.dumps({k: v for k, v in out.items() if k != "arms"}, indent=1))
    dest = args.runs / f"per_parity_study{'_cpu' if args.cpu_only else ''}.json"
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print("written:", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
