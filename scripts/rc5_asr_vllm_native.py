#!/usr/bin/env python3
"""rc5_asr_vllm_native.py — E2 on ROCm: Qwen3-ASR through a vLLM engine (RC5 M6, E2).

The official evaluator runs Qwen3-ASR-1.7B through vLLM 0.14.0 with the model
class bundled in qwen_asr 0.0.6. Neither is available on ROCm here (the
official ROCm wheel index is blocked; qwen_asr's backend imports vLLM 0.14
internals such as ``vllm.inputs.data`` that no longer exist in 0.19.1).

This runner keeps what the official path does around the engine and swaps
only the engine's model implementation for vLLM's native one:

    SAME  audio loading + 1200 s chunking (qwen_asr.inference.utils)
    SAME  prompt: the model's chat template applied to
          [system: context, user: [audio]] (qwen_asr's processor class)
    SAME  greedy decoding: temperature 0.0, max_tokens = official cap
    SAME  output parsing: qwen_asr.inference.utils.parse_asr_output
    DIFF  vLLM 0.19.1 native Qwen3ASRForConditionalGeneration instead of
          vLLM 0.14.0 + the qwen_asr-bundled model class

It writes TRANSCRIPTS (local only, never published). Scoring is a separate
step in the official metrics venv (scripts/rc5_score_transcripts.py) with the
official phoneme scorer.

Usage (portable vLLM environment, GPU lock held by the caller):
  python scripts/rc5_asr_vllm_native.py --asr-root DIR --manifest audio_manifest.jsonl \
      --out transcripts.jsonl [--repeats 4] [--max-new-tokens 4096] [--batch-songs 4] [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rc6_asr_identity as asr_id  # RC6 A2: fail-closed identity + resume

os.environ.setdefault("VLLM_NO_USAGE_STATS", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asr-root", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--repeats", type=int, default=4)
    ap.add_argument("--max-new-tokens", type=int, default=4096)
    ap.add_argument("--batch-songs", type=int, default=4,
                    help="songs whose chunks are submitted together (vLLM batches the chunks)")
    ap.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    import torch
    import vllm
    # ROCm bring-up (E2): vLLM 0.19.1's ROCm platform probe imports the amdsmi
    # python package; the shim on this host makes amdsmi_shut_down() raise
    # AMDSMI_STATUS_NOT_INIT after a SUCCESSFUL init + handle query, so the
    # plugin swallows its own success and vLLM falls through to
    # UnspecifiedPlatform (device_type='' -> 'Device string must not be
    # empty'). Registering the ROCm platform directly (the same class the
    # probe would return) is disclosed in the environment receipt.
    import vllm.platforms as _vp
    from vllm.platforms import rocm as _rocm
    if type(_vp.current_platform).__name__ == "UnspecifiedPlatform":
        sys.path.insert(0, "/usr/local/lib/python3.12/dist-packages/"
                           "_rocm_sdk_core/share/amd_smi")
        _vp._current_platform = _rocm.RocmPlatform()
    from vllm import LLM, SamplingParams
    from qwen_asr.inference.utils import (normalize_audios, split_audio_into_chunks, parse_asr_output,
                                          SAMPLE_RATE, MAX_ASR_INPUT_SECONDS)
    from qwen_asr.core.transformers_backend.processing_qwen3_asr import Qwen3ASRProcessor
    rows = [json.loads(l) for l in a.manifest.read_text().splitlines() if l.strip()]
    rows.sort(key=lambda r: (r["prompt_index"], r["candidate_index"]))
    if a.ids:
        want = set(a.ids.split(","))
        rows = [r for r in rows if r["id"] in want]
    if a.limit:
        rows = rows[:a.limit]
    # RC6 A2.1: full ASR_RUN_IDENTITY (model files, preprocessor, engine,
    # chunking sources, decoding, manifest, driver) computed BEFORE any GPU
    # work; every receipt embeds it.
    import qwen_asr
    from qwen_asr.inference import utils as _qa_utils
    run_identity = asr_id.build_run_identity(
        model_root=a.asr_root,
        engine={"engine": "vLLM native Qwen3ASRForConditionalGeneration on ROCm",
                "engine_class": "vllm.LLM(Qwen3ASRForConditionalGeneration)",
                "vllm": vllm.__version__, "torch": torch.__version__, "hip": torch.version.hip,
                "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                "platform": "RocmPlatform (registered directly, amdsmi probe shim)",
                "dtype": a.dtype},
        preproc={"audio_loading": "qwen_asr.inference.utils.normalize_audios",
                 "chunking": "qwen_asr.inference.utils.split_audio_into_chunks",
                 "utils_sha256": asr_id.sha256_file(
                     Path(_qa_utils.__file__)),
                 "sample_rate": 16000},
        decoding={"temperature": 0.0, "top_p": 1.0, "top_k": -1,
                  "max_tokens": a.max_new_tokens, "seed": a.seed,
                  "repeats": a.repeats, "batch_songs": a.batch_songs,
                  "gpu_memory_utilization": a.gpu_memory_utilization},
        scoring={"scorer_step": "scripts/rc5_score_transcripts.py (separate scoring identity)",
                 "audio_manifest_sha256": asr_id.sha256_file(a.manifest)},
        driver_path=Path(__file__).resolve())
    run_identity["engine"]["vllm"] = vllm.__version__
    run_identity["engine"]["qwen_asr"] = getattr(qwen_asr, "__version__",
                                                 Path(qwen_asr.__file__).parent.name)
    run_identity["run_identity_sha256"] = asr_id.sha256_bytes(
        json.dumps({k: v for k, v in run_identity.items() if k != "run_identity_sha256"},
                   sort_keys=True, ensure_ascii=False).encode())
    processor = Qwen3ASRProcessor.from_pretrained(str(a.asr_root))
    t0 = time.time()
    llm = LLM(model=str(a.asr_root), dtype=a.dtype, seed=a.seed,
              gpu_memory_utilization=a.gpu_memory_utilization,
              limit_mm_per_prompt={"audio": 3})
    load_s = time.time() - t0
    env = {"schema": "yue2-rc5-asr-engine/1", "engine": "vLLM native Qwen3ASRForConditionalGeneration on ROCm",
           "vllm": vllm.__version__, "torch": torch.__version__, "hip": torch.version.hip,
           "gpu": torch.cuda.get_device_name(0), "dtype": a.dtype, "seed": a.seed,
           "gpu_memory_utilization": a.gpu_memory_utilization, "max_new_tokens": a.max_new_tokens,
           "load_seconds": round(load_s, 1), "asr_root": str(a.asr_root),
           "run_identity": run_identity}
    try:
        from vllm.platforms import current_platform
        env["vllm_platform"] = type(current_platform).__name__
    except Exception:  # noqa: BLE001
        pass
    sampling = SamplingParams(temperature=0.0, top_p=1.0, top_k=-1, max_tokens=a.max_new_tokens)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    # RC6 A2.2: FAIL-CLOSED resume — never skip on candidate_id alone.
    done = set()
    if a.out.is_file():
        audit = asr_id.audit_receipts(a.out, rows, run_identity, expected_repeats=a.repeats)
        audit_out = a.out.with_suffix(a.out.suffix + ".resume_audit.json")
        audit_out.write_text(json.dumps(audit, indent=1, sort_keys=True) + "\n")
        if audit["invalid_tail_lines"]:
            q = asr_id.quarantine_tail(a.out, audit["valid_line_indices"])
            print(f"[resume] invalid JSONL tail: original moved to {q} "
                  f"({len(audit['invalid_tail_lines'])} bad lines dropped), re-auditing")
            audit = asr_id.audit_receipts(a.out, rows, run_identity, expected_repeats=a.repeats)
            audit_out.write_text(json.dumps(audit, indent=1, sort_keys=True) + "\n")
        if audit["duplicate_candidate_ids"]:
            print(json.dumps({"resume": "REFUSED", "reason": asr_id.R_DUPLICATE,
                              "duplicates": audit["duplicate_candidate_ids"]}))
            return 3
        if audit["rejected"]:
            print(json.dumps({"resume": "REFUSED", "reason": "rejected receipts present",
                              "rejected": audit["rejected"],
                              "hint": "start a NEW --out path (supersede, never overwrite)"}))
            return 4
        if audit["missing_from_file"]:
            print(f"[resume] {len(audit['missing_from_file'])} candidate(s) missing "
                  f"(will run); {len(audit['incomplete'])} incomplete (will re-run)")
        done = set(audit["reusable"])
    with a.out.open("a") as fout:
        for start in range(0, len(rows), a.batch_songs):
            batch = [r for r in rows[start:start + a.batch_songs] if r["id"] not in done]
            if not batch:
                continue
            t1 = time.time()
            wavs = normalize_audios([r["audio_path"] for r in batch])
            inputs, owner = [], []
            for r, wav in zip(batch, wavs):
                for _ in range(a.repeats):
                    for cwav, _off in split_audio_into_chunks(wav=wav, sr=SAMPLE_RATE,
                                                              max_chunk_sec=MAX_ASR_INPUT_SECONDS):
                        messages = [{"role": "system", "content": ""},
                                    {"role": "user", "content": [{"type": "audio", "audio": "audio"}]}]
                        prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                        inputs.append({"prompt": prompt, "multi_modal_data": {"audio": [cwav]}})
                        owner.append(r["id"])
            outputs = llm.generate(inputs, sampling_params=sampling, use_tqdm=False)
            per_song: dict[str, list] = {}
            for oid, o in zip(owner, outputs):
                per_song.setdefault(oid, []).append(
                    {"text_raw": o.outputs[0].text, "generated_tokens": len(o.outputs[0].token_ids),
                     "finish_reason": o.outputs[0].finish_reason})
            torch.cuda.synchronize()
            elapsed = time.time() - t1
            for r in batch:
                recs = per_song[r["id"]]
                n_chunks = len(recs) // a.repeats
                reps = []
                for i in range(a.repeats):
                    chunk_recs = recs[i * n_chunks:(i + 1) * n_chunks]
                    lang, txt = parse_asr_output("".join(c["text_raw"] for c in chunk_recs))
                    reps.append({"repeat": i, "language": lang, "text": txt, "raw_chunks": chunk_recs})
                receipt = {"id": r["id"], "prompt_index": r["prompt_index"],
                           "candidate_index": r["candidate_index"], "lang": r["lang"],
                           "audio_sha256": hashlib.sha256(Path(r["audio_path"]).read_bytes()).hexdigest(),
                           "chunks": n_chunks, "repeats": reps, "engine": env,
                           "run_identity": run_identity, "repeat_count": len(reps),
                           "status": "complete",
                           "batch_seconds": round(elapsed, 2)}
                receipt["transcript_receipt_sha256"] = asr_id.receipt_sha256(receipt)
                fout.write(json.dumps(receipt, ensure_ascii=False) + "\n")
                fout.flush()
                empties = sum(1 for x in reps if not x["text"].strip())
                caps = sum(1 for x in reps if any(c["finish_reason"] == "length" for c in x["raw_chunks"]))
                print(f"[vllm-asr] {r['id']} {r['lang']}: empty_repeats={empties}/{a.repeats} cap_repeats={caps} "
                      f"chars={[len(x['text']) for x in reps]} ({elapsed:.1f}s for {len(batch)} song(s))", flush=True)
    (a.out.with_suffix(".engine.json")).write_text(json.dumps(env, indent=1) + "\n")
    print(json.dumps(env))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
