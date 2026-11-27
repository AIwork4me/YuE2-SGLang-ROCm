#!/usr/bin/env python3
"""rc5_asr_reference.py — INDEPENDENT reference ASR for the PER study (RC5 M6, E4).

Transcribes the same official audio (same bytes, SHA256 recorded) with a
different, unrelated ASR family (OpenAI Whisper via Transformers) and scores
the transcript with the OFFICIAL phoneme scorer of the frozen evaluator
(historical_per.PerScorer: same cleaning, g2p phonemization, edit distance).

Purpose: diagnosis only. It answers one question per candidate — "is the
singing intelligible at all?" — without using the model under study. It is
NOT a WildSongBench metric and is never reported as PER.

  python scripts/rc5_asr_reference.py --evaluator-root R --manifest audio_manifest.jsonl \
      --model /path/whisper-large-v3-turbo --out DIR [--device cuda|cpu] [--ids a,b]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator-root", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="float16")
    ap.add_argument("--ids", default="")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    root = a.evaluator_root
    sys.path[:0] = [str(root / "src"), str(root / "vendor")]
    import nltk
    import torch
    import librosa
    from historical_per import PerScorer, edit_distance
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
    nltk.data.path[:] = [str(root / "evaluation_models/nltk_data")]
    for name in ["corpora/cmudict", "taggers/averaged_perceptron_tagger",
                 "taggers/averaged_perceptron_tagger_eng", "corpora/cmudict.zip",
                 "taggers/averaged_perceptron_tagger.zip"]:
        nltk.data.find(name)
    scorer = PerScorer()
    dtype = {"float16": torch.float16, "float32": torch.float32, "bfloat16": torch.bfloat16}[a.dtype]
    model = AutoModelForSpeechSeq2Seq.from_pretrained(str(a.model), torch_dtype=dtype).to(a.device).eval()
    processor = AutoProcessor.from_pretrained(str(a.model))
    rows = [json.loads(l) for l in a.manifest.read_text().splitlines() if l.strip()]
    rows.sort(key=lambda r: (r["prompt_index"], r["candidate_index"]))
    if a.ids:
        want = set(a.ids.split(","))
        rows = [r for r in rows if r["id"] in want]
    if a.limit:
        rows = rows[:a.limit]
    a.out.mkdir(parents=True, exist_ok=True)
    out_rows = []
    lang_code = {"zh": "zh", "en": "en"}
    for n, row in enumerate(rows, 1):
        t0 = time.time()
        try:
            sha = hashlib.sha256(Path(row["audio_path"]).read_bytes()).hexdigest()
            wav, sr = librosa.load(row["audio_path"], sr=16000, mono=True)
            forced = lang_code.get(row["lang"])
            gen_kw = dict(do_sample=False, max_new_tokens=440)
            if forced:
                gen_kw["language"] = forced
            # WhisperProcessor TRUNCATES to one 30 s window: long-form audio
            # must be split explicitly (first version of this script silently
            # transcribed only the first 30 s of every song).
            win = 30 * 16000
            windows = [wav[i:i + win] for i in range(0, len(wav), win)]
            pieces, n_tok = [], 0
            for i in range(0, len(windows), 8):
                chunk = windows[i:i + 8]
                inputs = processor(chunk, sampling_rate=16000, return_tensors="pt")
                feats = inputs.input_features.to(a.device, dtype=dtype)
                with torch.inference_mode():
                    ids = model.generate(feats, **gen_kw)
                n_tok += int(ids.shape[1])
                pieces.extend(processor.batch_decode(ids, skip_special_tokens=True))
            text = " ".join(x.strip() for x in pieces if x and x.strip())
            tokens = scorer.tokens(text)
            ref = scorer.tokens(row["target"]["reference_lyrics"])
            edits = edit_distance(tokens, ref)
            rec = {"id": row["id"], "prompt_index": row["prompt_index"],
                   "candidate_index": row["candidate_index"], "lang": row["lang"],
                   "audio_sha256": sha, "whisper_language_forced": forced,
                   "text": text, "transcript_chars": len(text), "phonemes": len(tokens),
                   "audio_seconds": round(len(wav) / 16000, 1), "whisper_windows_30s": len(windows),
                   "reference_phonemes": len(ref), "edits": edits,
                   "reference_per": round(edits / len(ref), 6) if ref else None,
                   "seconds": round(time.time() - t0, 2), "status": "complete"}
        except Exception as exc:  # noqa: BLE001
            rec = {"id": row.get("id"), "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        out_rows.append(rec)
        print(f"[ref-asr] {n}/{len(rows)} {rec['id']}: {rec['status']} chars={rec.get('transcript_chars')} "
              f"reference_per={rec.get('reference_per')} {rec.get('seconds')}s", flush=True)
    (a.out / "reference_asr.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out_rows))
    ok = [r for r in out_rows if r["status"] == "complete"]
    summary = {"schema": "yue2-rc5-reference-asr/1",
               "model": f"openai/whisper-large-v3-turbo ({a.model})", "device": a.device, "dtype": a.dtype,
               "scoring": "official historical_per.PerScorer phonemization + edit distance (diagnostic only; NOT PER)",
               "n": len(ok), "failed": len(out_rows) - len(ok),
               "micro_reference_per": round(sum(r["edits"] for r in ok) / max(1, sum(r["reference_phonemes"] for r in ok)), 6),
               "macro_reference_per": round(sum(r["reference_per"] for r in ok) / max(1, len(ok)), 6),
               "empty_transcripts": sum(1 for r in ok if r["transcript_chars"] == 0)}
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
