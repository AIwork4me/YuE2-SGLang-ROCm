#!/usr/bin/env python3
"""rc5_per_lab.py — controlled single-factor ASR/PER experiments (RC5 M6.4).

Same audio bytes, same evaluator code, same reference lyrics; ONE factor
changes per arm. Scoring is the OFFICIAL code path:

    mot_infer.eval_worker.PERScorer.score_batch(rows)      (verbatim)
        -> asr_repeats transcriptions of the official audio
        -> phoneme_result(scorer, reference, hypotheses)    (verbatim)
             g2p phonemization, edit distance, repeat selection, PER

Only the ASR ENGINE CONSTRUCTION differs per arm (the same place the
disclosed ROCm patch 0007 differs from the vLLM branch):

    dtype (bfloat16 | float32)      attention (sdpa | eager)
    batch size (8 official | 1)     cap (4096 official | other, labelled)
    audio container (official MP3 | candidate FLAC)
    language (auto, official | explicit, DIAGNOSTIC ONLY)

Outputs (LOCAL; transcripts are never published):
    <out>/<arm>/rows.jsonl      per candidate: official PER result + S/D/I split
    <out>/<arm>/environment.json engine facts
    <out>/summary.json          per-arm micro/macro PER, paired deltas vs the
                                baseline arm, prompt-level bootstrap CIs

Usage (inside the official metrics venv, GPU lock held by the caller):
  python scripts/rc5_per_lab.py --evaluator-root R --manifest audio_manifest.jsonl \
      --out DIR --arm baseline --arm batch1:batch_size=1 [...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
import traceback
from pathlib import Path

ARM_FACTORS = ("dtype", "attn", "batch_size", "max_new_tokens", "audio", "language", "repeats")
BASELINE = {"dtype": "bfloat16", "attn": None, "batch_size": 8, "max_new_tokens": 4096,
            "audio": "mp3", "language": "auto", "repeats": None}
LANG_MAP = {"zh": "Chinese", "en": "English"}


def parse_arm(spec: str) -> tuple[str, dict]:
    name, _, rest = spec.partition(":")
    factors = dict(BASELINE)
    for kv in filter(None, rest.split(",")):
        k, _, v = kv.partition("=")
        if k not in ARM_FACTORS:
            raise SystemExit(f"unknown factor {k!r} in arm {spec!r}")
        if k in ("batch_size", "max_new_tokens", "repeats"):
            v = int(v) if v else None
        factors[k] = v
    return name, factors


# ------------------------------------------------------------- statistics
def sdi(ref: list, hyp: list) -> dict:
    """Levenshtein alignment -> substitution / deletion / insertion counts."""
    n, m = len(ref), len(hyp)
    # full matrix (sequences are a few hundred phonemes)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        ri = ref[i - 1]
        row, prev = d[i], d[i - 1]
        for j in range(1, m + 1):
            c = 0 if ri == hyp[j - 1] else 1
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + c)
    s = dele = ins = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            if ref[i - 1] != hyp[j - 1]:
                s += 1
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            dele += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return {"substitutions": s, "deletions": dele, "insertions": ins, "edits": s + dele + ins}


def bootstrap_ci(values: list[float], reps: int = 2000, seed: int = 20261124) -> dict:
    if not values:
        return {"mean": None, "ci95": None, "n": 0}
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(reps))
    return {"mean": round(sum(values) / n, 6), "ci95": [round(means[int(0.025 * reps)], 6),
                                                      round(means[int(0.975 * reps) - 1], 6)], "n": n}


def micro(rows: list[dict]) -> dict:
    e = sum(r["edits"] for r in rows)
    n = sum(r["reference_phonemes"] for r in rows)
    return {"micro_per": round(e / n, 6) if n else None, "edits": e, "reference_phonemes": n,
            "macro_per": round(sum(r["per"] for r in rows) / len(rows), 6) if rows else None,
            "n": len(rows)}


# --------------------------------------------------------------- engine
def build_scorer(root: Path, config: dict, factors: dict):
    """The official PERScorer with the transformers branch of its __init__
    parametrised by the arm (patch 0007 location); scoring methods untouched."""
    import torch
    import nltk
    sys.path[:0] = [str(root / "src"), str(root / "vendor")]
    from historical_per import PerScorer
    from qwen_asr import Qwen3ASRModel
    from mot_infer import eval_worker
    from mot_infer.eval_assets import model_path
    nltk.data.path[:] = [str(root / "evaluation_models/nltk_data")]
    for name in ["corpora/cmudict", "taggers/averaged_perceptron_tagger",
                 "taggers/averaged_perceptron_tagger_eng", "corpora/cmudict.zip",
                 "taggers/averaged_perceptron_tagger.zip"]:
        nltk.data.find(name)
    s = eval_worker.PERScorer.__new__(eval_worker.PERScorer)
    s.scorer = PerScorer()
    s.config = dict(config["per"])
    cap = factors["max_new_tokens"] or s.config["max_new_tokens"]
    s.config["max_new_tokens"] = cap
    if factors["repeats"]:
        s.config["asr_repeats"] = int(factors["repeats"])
    kw = {"dtype": {"bfloat16": torch.bfloat16, "float32": torch.float32}[factors["dtype"]],
          "max_inference_batch_size": int(factors["batch_size"]), "max_new_tokens": cap}
    if factors["attn"]:
        kw["attn_implementation"] = factors["attn"]
    t0 = time.time()
    s.model = Qwen3ASRModel.from_pretrained(str(model_path(root, "asr")), **kw)
    s.model.model.to("cuda")
    s.model.device = s.model.model.device
    s.load_s = round(time.time() - t0, 1)
    s.raw = []
    original = s.model.model.generate

    def record(*args, **kwargs):
        # identical to the disclosed ROCm patch 0007
        outputs = original(*args, **kwargs)
        cap_ = s.model.max_new_tokens or s.config["max_new_tokens"]
        prompt_len = kwargs["input_ids"].shape[1]
        sequences = outputs.sequences if hasattr(outputs, "sequences") else outputs[0]
        continuations = sequences[:, prompt_len:]
        texts = s.model.processor.batch_decode(continuations, skip_special_tokens=True,
                                               clean_up_tokenization_spaces=False)
        for text, row in zip(texts, continuations):
            n = int(row.shape[0])
            s.raw.append({"text": text, "generated_tokens": n,
                          "finish_reason": "length" if n >= cap_ else "stop"})
        return outputs
    s.model.model.generate = record
    s._factors = factors
    return s


def score_rows(s, rows: list[dict], factors: dict) -> list[dict]:
    """Official scoring. Only the explicit-language arm (diagnostic) deviates
    from score_batch, by passing a language instead of None."""
    from mot_infer.eval_worker import phoneme_result
    from qwen_asr.inference.utils import (normalize_audios, split_audio_into_chunks, SAMPLE_RATE,
                                          MAX_ASR_INPUT_SECONDS)
    out = []
    bs = int(factors["batch_size"])
    for start in range(0, len(rows), bs):
        batch = rows[start:start + bs]
        t0 = time.time()
        try:
            if factors["language"] == "auto":
                results = s.score_batch(batch)             # official method
            else:
                # DIAGNOSTIC arm: same steps as score_batch with an explicit language
                paths = [r["audio_path"] for r in batch]
                counts = [len(split_audio_into_chunks(wav, SAMPLE_RATE, MAX_ASR_INPUT_SECONDS))
                          for wav in normalize_audios(paths)]
                langs = [LANG_MAP.get(r["lang"]) for r in batch]
                hypotheses = [[] for _ in batch]
                for _ in range(s.config["asr_repeats"]):
                    s.raw = []
                    results_ = s.model.transcribe(audio=paths, language=langs)
                    if len(results_) != len(batch) or len(s.raw) != sum(counts):
                        raise ValueError("ASR output/chunk count mismatch")
                    offset = 0
                    for i, (result, count) in enumerate(zip(results_, counts)):
                        hypotheses[i].append({"text": result.text, "language": result.language,
                                              "raw_chunks": s.raw[offset:offset + count]})
                        offset += count
                results = [phoneme_result(s.scorer, row["target"]["reference_lyrics"], rep)
                           for row, rep in zip(batch, hypotheses)]
        except Exception as exc:  # noqa: BLE001 - recorded like the evaluator does
            results = [{"status": "failed", "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc()} for _ in batch]
        import torch
        torch.cuda.synchronize()
        elapsed = time.time() - t0
        for row, res in zip(batch, results):
            res["batch_seconds"] = round(elapsed, 2)
            res["batch_size"] = len(batch)
            res["id"] = row["id"]
            res["prompt_index"] = row["prompt_index"]
            res["candidate_index"] = row["candidate_index"]
            res["lang"] = row["lang"]
            res["audio_sha256"] = row.get("audio_sha256")
            if res.get("status") == "complete":
                sel = res["asr_repeats"][res["selected_asr_repeat"]]
                res["sdi"] = sdi(res["reference_tokens"], sel["phonemes"])
                res["empty_transcript_repeats"] = sum(1 for r in res["asr_repeats"] if not r["text"].strip())
            out.append(res)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator-root", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True, help="official audio_manifest.jsonl")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--arm", action="append", required=True,
                    help="name[:factor=value,...]; the first arm is the baseline")
    ap.add_argument("--ids", default="")
    ap.add_argument("--flac-dir", type=Path, default=None,
                    help="candidate songs/ dir for the audio=flac arm")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    root = a.evaluator_root
    config = json.loads((root / "configs/evaluation.json").read_text())
    rows = [json.loads(l) for l in a.manifest.read_text().splitlines() if l.strip()]
    rows.sort(key=lambda r: (r["prompt_index"], r["candidate_index"]))
    if a.ids:
        want = set(a.ids.split(","))
        rows = [r for r in rows if r["id"] in want]
    if a.limit:
        rows = rows[:a.limit]
    a.out.mkdir(parents=True, exist_ok=True)
    arms = [parse_arm(x) for x in a.arm]
    import torch
    summary = {"schema": "yue2-rc5-per-lab/1", "n_candidates": len(rows), "arms": {}}
    per_arm: dict[str, list[dict]] = {}
    for name, factors in arms:
        dest = a.out / name
        dest.mkdir(parents=True, exist_ok=True)
        arm_rows = rows
        if factors["audio"] == "flac":
            if not a.flac_dir:
                raise SystemExit("--flac-dir required for the audio=flac arm")
            arm_rows = [{**r, "audio_path": str(a.flac_dir / r["id"] / "audio.flac")} for r in rows]
        print(f"[per-lab] arm {name}: {factors}", flush=True)
        scorer = build_scorer(root, config, factors)
        t0 = time.time()
        results = score_rows(scorer, arm_rows, factors)
        (dest / "rows.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results))
        env = {"schema": "yue2-rc5-per-lab-arm/1", "arm": name, "factors": factors, "load_s": scorer.load_s,
               "score_seconds": round(time.time() - t0, 1),
               "attn_implementation": getattr(scorer.model.model.config, "_attn_implementation", None),
               "torch": torch.__version__, "hip": torch.version.hip,
               "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
               "asr_config": scorer.config,
               "evaluator_eval_worker_sha256": hashlib.sha256((root / "src/mot_infer/eval_worker.py").read_bytes()).hexdigest(),
               "asr_model_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                                    for p in sorted((root / json.loads((root / "configs/evaluation_assets.json").read_text())["models"]["asr"]["path"]).glob("*.safetensors"))}}
        (dest / "environment.json").write_text(json.dumps(env, indent=1) + "\n")
        ok = [r for r in results if r.get("status") == "complete"]
        per_arm[name] = ok
        summary["arms"][name] = {
            "factors": factors, **micro(ok), "failed": len(results) - len(ok),
            "empty_transcript_candidates": sum(1 for r in ok if r["empty_transcript_repeats"] == len(r["asr_repeats"])),
            "candidates_with_any_empty_repeat": sum(1 for r in ok if r["empty_transcript_repeats"] > 0),
            "truncated_repeats": sum(r["truncated_repeats"] for r in ok),
            "sdi_totals": {k: sum(r["sdi"][k] for r in ok) for k in ("substitutions", "deletions", "insertions")},
            "mean_generated_tokens": round(sum(c["generated_tokens"] for r in ok for x in r["asr_repeats"]
                                             for c in x.get("raw_chunks", [])) / max(1, sum(len(r["asr_repeats"]) for r in ok)), 1),
            "repeat_determinism": {"candidates_with_identical_repeats": sum(
                1 for r in ok if len({x["text"] for x in r["asr_repeats"]}) == 1), "n": len(ok)},
            "score_seconds": env["score_seconds"]}
        print(f"[per-lab]   {name}: {json.dumps({k: summary['arms'][name][k] for k in ('micro_per', 'macro_per', 'n', 'failed', 'empty_transcript_candidates', 'truncated_repeats', 'score_seconds')})}", flush=True)
        del scorer
        torch.cuda.empty_cache()
    base = arms[0][0]
    for name in [n for n, _ in arms[1:]]:
        b = {r["id"]: r for r in per_arm[base]}
        pairs = [(b[r["id"]], r) for r in per_arm[name] if r["id"] in b]
        d_per = [r["per"] - b_["per"] for b_, r in pairs]
        d_tok = [r["asr_repeats"][r["selected_asr_repeat"]]["generated_tokens"]
                 - b_["asr_repeats"][b_["selected_asr_repeat"]]["generated_tokens"] for b_, r in pairs]
        changed = sum(1 for b_, r in pairs
                      if [x["text"] for x in b_["asr_repeats"]] != [x["text"] for x in r["asr_repeats"]])
        # prompt-level bootstrap: average candidate deltas within a prompt, resample prompts
        by_prompt: dict[int, list[float]] = {}
        for b_, r in pairs:
            by_prompt.setdefault(r["prompt_index"], []).append(r["per"] - b_["per"])
        summary["arms"][name]["vs_baseline"] = {
            "baseline": base, "pairs": len(pairs),
            "micro_per_delta_pp": round((summary["arms"][name]["micro_per"] - summary["arms"][base]["micro_per"]) * 100, 4),
            "candidates_with_changed_transcripts": changed,
            "mean_selected_generated_tokens_delta": round(sum(d_tok) / len(d_tok), 2) if d_tok else None,
            "candidate_per_delta": bootstrap_ci(d_per),
            "prompt_per_delta": bootstrap_ci([sum(v) / len(v) for v in by_prompt.values()])}
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({n: {"micro_per": v["micro_per"], "macro_per": v["macro_per"],
                          "empty": v["empty_transcript_candidates"], "trunc": v["truncated_repeats"]}
                      for n, v in summary["arms"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
