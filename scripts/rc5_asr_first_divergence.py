#!/usr/bin/env python3
"""rc5_asr_first_divergence.py — RC5.1 P1.1.4 source-level first-divergence probe.

For the DETERMINISTIC empty-transcript candidates: same audio bytes, same
official preprocessing, teacher-forced on the SAME token prefix; compares
stage-by-stage numeric fingerprints across ASR engine configurations
(precision / device / attention) to locate the FIRST divergence:

    audio bytes -> feature tensor (hash, shape, min/max/mean/std)
                -> encoder hidden states (per-stage stats)
                -> logits at decode step 1..K (top-k, EOS logit/rank/prob,
                   language-token probability)
                -> first differing decode step

Every cell is recorded; nothing is tuned. The probe never claims what the
official CUDA vLLM engine would do (no CUDA host: BLOCKED_EXTERNAL).

Usage (metrics venv, GPU lock held by the caller):
  python scripts/rc5_asr_first_divergence.py --evaluator-root R \
      --manifest rc5_1_matrix_manifest.jsonl --out DIR [--ids a,b] [--steps 12]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def sha_t(t) -> str:
    import torch
    return hashlib.sha256(t.detach().float().cpu().contiguous().numpy().tobytes()).hexdigest()


def stats(t) -> dict:
    f = t.detach().float()
    return {"sha256": sha_t(t), "shape": list(t.shape),
            "min": round(float(f.min()), 6), "max": round(float(f.max()), 6),
            "mean": round(float(f.mean()), 6), "std": round(float(f.std()), 6)}


def probe_config(model, torch, row, steps: int, eos_id: int) -> dict:
    """Run one engine config on one row, replicating the OFFICIAL input path:
    qwen_asr._build_text_prompt (context='', no forced language) + the model's
    own audio normalisation/chunking, then teacher-forced greedy decoding with
    per-step logit capture."""
    from qwen_asr.inference.utils import normalize_audios, split_audio_into_chunks, SAMPLE_RATE
    wav = normalize_audios(row["audio_path"])[0]
    chunks = split_audio_into_chunks(wav=wav, sr=SAMPLE_RATE, max_chunk_sec=1200)
    first = chunks[0]
    wav_chunk = first.wav if hasattr(first, "wav") and first.wav is not None else first[0]
    prompt = model._build_text_prompt(context="", force_language=None)
    inputs = model.processor(text=[prompt], audio=[wav_chunk], return_tensors="pt", padding=True)
    feats = {k: stats(v) for k, v in inputs.items() if hasattr(v, "shape")}
    moved = {}
    for k, v in inputs.items():
        if hasattr(v, "to"):
            dt = torch.float32 if v.is_floating_point() and model.model.dtype == torch.float32 \
                else (torch.bfloat16 if v.is_floating_point() else None)
            moved[k] = v.to(model.model.device, dt) if dt else v.to(model.model.device)
        else:
            moved[k] = v
    n_in = moved["input_ids"].shape[1]
    out = {"features": feats, "input_tokens": int(n_in), "decode_steps": [],
           "chunks": len(chunks)}
    t0 = time.time()
    res = model.model.generate(**moved, do_sample=False, max_new_tokens=steps,
                               output_scores=True,
                               eos_token_id=None)      # observe, never stop early
    # the wrapper fixes return_dict_in_generate=True internally; scores and
    # sequences are present on its GenerateDecoderOnlyOutput-style result
    cont = res.sequences[0][n_in:]
    for i, sc in enumerate(res.scores[:steps]):
        sc = sc[0].float()
        probs = torch.softmax(sc, -1)
        top = torch.topk(sc, 5)
        out["decode_steps"].append({
            "step": i + 1,
            "chosen_token": int(cont[i]),
            "top5_tokens": top.indices.tolist(),
            "top5_probs": [round(float(probs[t]), 8) for t in top.indices.tolist()],
            "eos_logit": round(float(sc[eos_id]), 4),
            "eos_rank": int((sc > sc[eos_id]).sum()),
            "eos_prob": round(float(probs[eos_id]), 8),
        })
    out["seconds"] = round(time.time() - t0, 1)
    out["generated_prefix"] = cont.tolist()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator-root", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--steps", type=int, default=12)
    a = ap.parse_args()
    sys.path[:0] = [str(a.evaluator_root / "src"), str(a.evaluator_root / "vendor")]
    import torch
    from qwen_asr import Qwen3ASRModel
    from mot_infer.eval_assets import model_path
    rows = [json.loads(l) for l in a.manifest.read_text().splitlines() if l.strip()]
    if a.ids:
        want = set(a.ids.split(","))
        rows = [r for r in rows if r["id"] in want]
    a.out.mkdir(parents=True, exist_ok=True)
    CONFIGS = [
        ("gpu_bf16_sdpa", {"dtype": torch.bfloat16, "device": "cuda", "attn": "sdpa"}),
        ("gpu_fp32_sdpa", {"dtype": torch.float32, "device": "cuda", "attn": "sdpa"}),
        ("gpu_bf16_eager", {"dtype": torch.bfloat16, "device": "cuda", "attn": "eager"}),
        ("cpu_fp32", {"dtype": torch.float32, "device": "cpu", "attn": "sdpa"}),
    ]
    report = {"schema": "yue2-rc5_1-asr-first-divergence/1",
              "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "steps": a.steps, "configs": [c[0] for c in CONFIGS], "rows": {}}
    for name, cfg in CONFIGS:
        kw = {"dtype": cfg["dtype"], "max_inference_batch_size": 1, "max_new_tokens": a.steps}
        if cfg.get("attn"):
            kw["attn_implementation"] = cfg["attn"]
        m = Qwen3ASRModel.from_pretrained(str(model_path(a.evaluator_root, "asr")), **kw)
        m.model.to(cfg["device"])
        eos = m.model.generation_config.eos_token_id
        eos = eos if isinstance(eos, int) else (eos[0] if isinstance(eos, list) and eos else 151645)
        for row in rows:
            rec = report["rows"].setdefault(row["id"], {})
            rec["audio_sha256"] = row.get("audio_sha256")
            rec[name] = probe_config(m, torch, row, a.steps, eos)
        del m
        if cfg["device"] == "cuda":
            torch.cuda.empty_cache()
        print(f"[first-div] config {name} done", flush=True)
    # first divergence per row / config pair
    for rid, rec in report["rows"].items():
        div = {}
        base = rec["gpu_bf16_sdpa"]
        for other in ("gpu_fp32_sdpa", "gpu_bf16_eager", "cpu_fp32"):
            o = rec[other]
            if base["features"] != o["features"]:
                div[other] = {"stage": "feature_extraction",
                              "differing_keys": [k for k in base["features"]
                                                 if base["features"][k] != o["features"].get(k)][:6]}
                continue
            first = None
            for s_b, s_o in zip(base["decode_steps"], o["decode_steps"]):
                if s_b["chosen_token"] != s_o["chosen_token"]:
                    first = {"step": s_b["step"],
                             "baseline_token": s_b["chosen_token"],
                             "other_token": s_o["chosen_token"],
                             "baseline_top5": s_b["top5_tokens"],
                             "other_top5": s_o["top5_tokens"],
                             "baseline_eos_prob": s_b["eos_prob"],
                             "other_eos_prob": s_o["eos_prob"]}
                    break
            div[other] = {"stage": "decode", "first_token_divergence": first}
        rec["first_divergence"] = div
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "first_divergence.json").write_text(json.dumps(report, indent=1) + "\n")
    for rid, rec in report["rows"].items():
        print(rid, json.dumps(rec["first_divergence"])[:240])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
