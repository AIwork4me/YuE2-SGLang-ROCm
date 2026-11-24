#!/usr/bin/env python3
"""rc5_asr_bench.py — timing / behaviour micro-benchmark of the official ASR
(Qwen3-ASR-1.7B via the qwen_asr transformers backend) on real audio (RC5 M6).

Measures where evaluator time goes and how single factors change the
transcript: attention implementation, dtype, batch size, cap. Nothing here
is a metric run; it is the instrument used to design the controlled PER
experiments.

Run inside the official metrics venv (lock held by the caller):
  python scripts/rc5_asr_bench.py --audio a.mp3 [b.mp3 ...] [--attn sdpa|eager]
      [--dtype bfloat16|float32] [--max-new-tokens 256] [--batch-size 1|8]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", type=Path, nargs="+", required=True)
    ap.add_argument("--asr-root", type=Path, required=True,
                    help="snapshot dir of Qwen3-ASR-1.7B")
    ap.add_argument("--attn", default=None)
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    import torch
    from qwen_asr import Qwen3ASRModel
    from qwen_asr.inference.utils import normalize_audios, split_audio_into_chunks, SAMPLE_RATE, MAX_ASR_INPUT_SECONDS
    dtype = {"bfloat16": torch.bfloat16, "float32": torch.float32}[a.dtype]
    t0 = time.time()
    kw = {"dtype": dtype, "max_inference_batch_size": a.batch_size, "max_new_tokens": a.max_new_tokens}
    if a.attn:
        kw["attn_implementation"] = a.attn
    m = Qwen3ASRModel.from_pretrained(str(a.asr_root), **kw)
    m.model.to("cuda")
    m.device = m.model.device
    load_s = time.time() - t0
    rec = {"attn_implementation": getattr(m.model.config, "_attn_implementation", None),
           "dtype": a.dtype, "load_s": round(load_s, 1), "batch_size": a.batch_size,
           "max_new_tokens": a.max_new_tokens, "runs": []}
    calls = []
    orig = m.model.generate

    def timed(*args, **kwargs):
        t = time.time()
        out = orig(*args, **kwargs)
        n_in = kwargs["input_ids"].shape[1]
        seqs = out.sequences if hasattr(out, "sequences") else out[0]
        cont = seqs[:, n_in:]
        torch.cuda.synchronize()
        calls.append({"seconds": round(time.time() - t, 3), "batch": int(n_in[0]) if hasattr(n_in, "__len__") else None,
                      "prompt_tokens": int(seqs.shape[1] - cont.shape[1]), "batch_rows": int(seqs.shape[0]),
                      "generated_tokens": [int(x) for x in (cont != m.processor.tokenizer.pad_token_id).sum(dim=1)] if m.processor.tokenizer.pad_token_id is not None else None})
        return out
    m.model.generate = timed
    for audio in a.audio:
        t1 = time.time()
        wav = normalize_audios([str(audio)])[0]
        chunks = split_audio_into_chunks(wav=wav, sr=SAMPLE_RATE, max_chunk_sec=MAX_ASR_INPUT_SECONDS)
        prep_s = time.time() - t1
        calls.clear()
        t1 = time.time()
        out = m.transcribe(audio=[str(audio)], language=None)[0]
        total_s = time.time() - t1
        torch.cuda.reset_peak_memory_stats()
        run = {"audio": str(audio), "audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
               "audio_seconds": round(len(wav) / SAMPLE_RATE, 1), "chunks": len(chunks),
               "prep_s": round(prep_s, 2), "transcribe_s": round(total_s, 2),
               "generate_calls": list(calls), "language": out.language,
               "transcript_chars": len(out.text), "transcript_sha256": hashlib.sha256(out.text.encode()).hexdigest(),
               "transcript_head": out.text[:80]}
        rec["runs"].append(run)
        print(json.dumps({k: v for k, v in run.items() if k != "transcript_head"}, ensure_ascii=False))
    if a.out:
        a.out.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: rec[k] for k in ("attn_implementation", "dtype", "load_s", "batch_size", "max_new_tokens")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
