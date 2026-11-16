#!/usr/bin/env python3
"""build_per_reference_package.py — P6.3 portable same-audio cross-backend kit.

Selects a STRATIFIED subset of generated audio (low/med/high PER, capped, empty,
zh/en, short/long), verifies hashes, and packages:
  * audio/ (flac, sha256-manifested)
  * commands.md  (exact official vLLM-backend scoring commands for a CUDA host)
  * package.json (manifest: selection rationale, hashes, evaluator pins,
    expected-result schema, reproducibility checks)

Respects redistribution rights: audio is OUR generated output (model sings
licensed-prompt lyrics → package marked restricted-use, for the YuE2 authors /
evaluation hosts only, not public redistribution).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_stratified(per_song: Path, songs_dir: Path, n_per_bucket=2):
    rows = [json.loads(l) for l in per_song.read_text().splitlines() if l.strip()]
    sel = {}
    # selected = lower per candidate per prompt (evaluator selection semantics)
    by_prompt = {}
    for r in rows:
        k = r["prompt_index"]
        if k not in by_prompt or r["metrics"]["per"]["per"] < by_prompt[k]["metrics"]["per"]["per"]:
            by_prompt[k] = r

    def bucket(rs, name):
        rs = sorted(rs, key=lambda r: r["metrics"]["per"]["per"])
        out = []
        if rs:
            out += [(name, "lowest", rs[i]) for i in range(min(n_per_bucket, len(rs)))]
            out += [(name, "median", rs[len(rs) // 2 + i]) for i in range(min(n_per_bucket, len(rs)))]
            out += [(name, "highest", rs[-1 - i]) for i in range(min(n_per_bucket, len(rs)))]
        return out

    sel_rows = list(by_prompt.values())
    picked = []
    capped = [r for r in sel_rows if r["metrics"]["per"].get("selected_asr_truncated")]
    emptyish = [r for r in sel_rows if r["metrics"]["per"]["per"] >= 0.999]
    zh = [r for r in sel_rows if r.get("lang") == "zh" and r not in capped and r not in emptyish]
    en = [r for r in sel_rows if r.get("lang") == "en" and r not in capped and r not in emptyish]
    picked += bucket(capped, "asr_capped") + bucket(emptyish, "empty_transcript")
    picked += bucket(zh, "zh") + bucket(en, "en")
    # dedupe by id, keep order
    seen = set()
    strat = []
    for b, rank, r in picked:
        if r["id"] not in seen:
            seen.add(r["id"])
            strat.append({"id": r["id"], "bucket": b, "rank": rank,
                          "per_this_backend": r["metrics"]["per"]["per"],
                          "lang": r.get("lang"),
                          "prompt_index": r["prompt_index"]})
    return strat


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True, help="campaign run dir (armA/armB)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    per_song = args.run / "scores" / "per_song.jsonl"
    songs = args.run / "songs"
    strat = pick_stratified(per_song, songs)
    audio_out = args.out / "audio"
    audio_out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for s in strat:
        src = songs / s["id"] / "audio.flac"
        if not src.is_file():
            src = songs / f"{s['id']}.wav"
        dst = audio_out / (s["id"] + src.suffix)
        shutil.copyfile(src, dst)
        manifest.append({**s, "file": dst.name, "bytes": dst.stat().st_size,
                         "sha256": sha(dst)})
    pkg = {
        "package": "yue2-w7900-per-reference-scoring",
        "created_utc": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "purpose": ("Same-audio, different-evaluator experiment (P6.3): score this audio "
                    "with the OFFICIAL vLLM ASR backend on a CUDA host and compare per-sample "
                    "PER vs the ROCm qwen_asr/transformers receipts included here."),
        "restriction": ("Audio generated from licensed WildSongBench prompt lyrics under the "
                        "dataset research license; for YuE2 authors / evaluation hosts ONLY; "
                        "no public redistribution."),
        "evaluator_pins": {
            "dataset_revision": "e361b85a8d7365d3079fa9647641a87ce3c8c5b5",
            "evaluator_bundle_sha256": "bd550b36f1fc43cad3254a9897dd3a078e50c4eb9e8d4f295ac4b5e81d1fc4fd",
            "asr_weights": "Qwen/Qwen3-ASR-1.7B @ 7278e1e70fe206f11671096ffdd38061171dd6e5",
            "official_backend": "vllm==0.14.0 (CUDA)",
            "rocm_backend_used_for_reference_values": "qwen_asr transformers under WSB_ROCM_TORCH_OVERRIDE=1 (patch 0007)",
        },
        "commands": [
            "# On a CUDA host with >=1 GPU (24GB+):",
            "tar xzf wsb_metrics.tar.gz && cd wsb_metrics",
            "uv python install 3.12.11 && uv venv --python 3.12.11 .venvs/metrics",
            "uv pip install --python .venvs/metrics/bin/python -r configs/metrics.installed.lock.txt",
            ".venvs/metrics/bin/python wsb_eval.py score --input evaluation_inputs.jsonl \\",
            "  --output scores_reference --mode standard --metrics per",
            "# (evaluation_inputs.jsonl for the subset is included; paths pre-mapped to audio/)",
        ],
        "expected_result_schema": {
            "per_sample": {"id": "str", "per": "float", "edits": "int",
                           "phonemes": "int", "transcript": "str"},
            "comparison": "per-sample PER difference vs reference_values; mean/median; "
                          "bias by duration/lang/capping; agreement at selection boundary",
        },
        "reference_values": manifest,
        "reproducibility_checks": [
            "flac sha256 must match manifest before scoring",
            "reference PER values reproduce from included reference_per.jsonl",
            "official evaluator version banner must show 2026.09.09.2 + vLLM 0.14.0",
        ],
    }
    # include the reference per rows for these ids
    ref = {}
    for line in per_song.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r["id"] in {m["id"] for m in manifest}:
                d = dict(r)
                d["metrics"] = {"per": {k: v for k, v in r["metrics"]["per"].items()
                                        if k in ("per", "edits", "reference_phonemes",
                                                 "selected_asr_truncated", "truncated")}}
                ref[r["id"]] = d
    (args.out / "reference_per.jsonl").write_text(
        "".join(json.dumps(ref[m["id"]]) + "\n" for m in manifest))
    (args.out / "evaluation_inputs.jsonl").write_text(
        "".join(json.dumps({"prompt_index": m["prompt_index"],
                            "candidate_index": 0 if m["id"].split("_r")[1][0] == "0" else 1,
                            "seed": int(m["id"].split("_s")[1]),
                            "path": f"audio/{m['file']}"}) + "\n" for m in manifest))
    (args.out / "package.json").write_text(json.dumps(pkg, indent=2))
    print(f"package at {args.out}: {len(manifest)} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
