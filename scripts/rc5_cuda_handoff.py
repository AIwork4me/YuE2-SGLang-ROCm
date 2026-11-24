#!/usr/bin/env python3
"""rc5_cuda_handoff.py — E3/E7 hand-off package for a CUDA host (RC5 M6.3).

No CUDA host is available on this bench, so the two experiments that need the
OFFICIAL environment (vLLM 0.14.0 + FlashAttention 2.8.3, CUDA GPU) are
prepared here as a self-describing package instead:

    pack         build HANDOFF_MANIFEST.json + README from a finished run:
                 run identity, checkpoint archives with SHA256, every
                 candidate id with the SHA256 of its official audio, the
                 evaluator identity and the exact official command
    restore-check  (CUDA host) verify the transferred checkpoints
    compare      (any host) CUDA vs ROCm PER, candidate by candidate

The package never contains lyrics or audio: the CUDA executor restores the
candidate bundles from the checkpoints (transferred separately by the owner)
and gets the reference lyrics from the frozen evaluator bundle.

    python scripts/rc5_cuda_handoff.py pack --run-dir D --out DIR
    python scripts/rc5_cuda_handoff.py restore-check --manifest M --backup-dir D
    python scripts/rc5_cuda_handoff.py compare --rocm per_song.jsonl \
        --cuda per_song.jsonl --out compare.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ pack
def cmd_pack(a) -> int:
    run = a.run_dir
    journal = [json.loads(l) for l in (run / "journal.jsonl").read_text().splitlines() if l.strip()]
    results = {}
    for e in journal:
        if e.get("event") == "result" and e.get("status") == "complete":
            results[e["id"]] = e
    cps = []
    for m in sorted((run / "checkpoints").glob("*.manifest.json")):
        arch = m.with_name(m.name.replace(".manifest.json", ".tar.zst"))
        if not arch.is_file():
            arch = m.with_name(m.name.replace(".manifest.json", ".tar"))
        cps.append({"archive": arch.name, "bytes": arch.stat().st_size,
                    "sha256": sha_file(arch), "kind": json.loads(m.read_text())["kind"]})
    cfg = json.loads((run / "run_config.json").read_text())
    evaluator = json.loads((a.evaluator_root / "release.json").read_text())
    manifest = {
        "schema": "yue2-rc5-cuda-handoff/1",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "why": "E3 (RC5 audio -> official CUDA vLLM ASR) and E7 cannot run on the ROCm bench: no CUDA host; "
               "the official ROCm vLLM wheel index is blocked by the bench egress proxy",
        "run": {"run_id": cfg.get("run_id"), "arm": cfg.get("arm"),
                "sglang_commit": (cfg.get("runtime") or {}).get("sglang_commit"),
                "sglang_tracked_diff_sha256": (cfg.get("runtime") or {}).get("sglang_tracked_diff_sha256"),
                "dataset_revision": cfg.get("dataset_revision"), "model_sha256": cfg.get("model_sha256"),
                "vae_sha256": cfg.get("vae_sha256"), "generation_config": cfg.get("config")},
        "candidates": {cid: {"audio_flac_sha256": r["audio_flac_sha256"],
                             "audio_seconds": round(r["audio_seconds"], 3), "truncated": r["truncated"],
                             "prompt_index": r["prompt_index"], "candidate_index": r["candidate_index"],
                             "seed": r["seed"]} for cid, r in sorted(results.items())},
        "checkpoints": cps,
        "evaluator": {"bundle_version": evaluator.get("version"),
                      "wsb_eval_sha256_pristine": "29310259f0ad3663bc2625ab80bf89c70d9206b513bcb2b4de5f47cb53cad9de",
                      "eval_worker_sha256_pristine": "8c6ffe394cfd8a40b4b972a53eb93ebf82569df14f60c04acf6826df1a63e4c4",
                      "asr_model": "Qwen/Qwen3-ASR-1.7B @ 7278e1e70fe206f11671096ffdd38061171dd6e5",
                      "asr_config": {"seed": 0, "asr_repeats": 4, "asr_batch_size": 8, "max_new_tokens": 4096,
                                     "gpu_memory_utilization": 0.85, "dtype": "bfloat16", "language": None,
                                     "temperature": 0.0}},
        "official_command_on_cuda": [
            "python wsb_eval.py prepare --metrics per --download huggingface --install",
            "python wsb_eval.py score --input <run>/evaluation_inputs.jsonl --output <run>/scores_cuda "
            "--mode standard --metrics per"],
        "rules": ["Do NOT set WSB_ROCM_TORCH_OVERRIDE (the official vLLM branch must run).",
                  "Do not regenerate audio: restore the candidate bundles from the checkpoints.",
                  "Return per_song.jsonl, protocol.json, per.environment.json and the receipts' SHA256 list."],
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "HANDOFF_MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
    (a.out / "README_CUDA_HANDOFF.md").write_text(_readme(manifest, a.run_dir))
    print(json.dumps({"candidates": len(manifest["candidates"]), "checkpoints": len(cps),
                      "bytes": sum(c["bytes"] for c in cps), "out": str(a.out)}))
    return 0


def _readme(m: dict, run: Path) -> str:
    return f"""# CUDA hand-off — official PER for run `{m['run']['run_id']}`

Goal: score the **same audio** with the official evaluator (vLLM 0.14.0 +
FlashAttention 2.8.3 on a CUDA GPU) so it can be compared with the ROCm PER.

## 1. Transfer and verify (the checkpoints hold the candidate bundles; no lyrics inside)

```bash
# on the bench: list archives + SHA256
python scripts/rc5_backup.py snapshots --from {run}
# on the CUDA host, after copying the checkpoint archives into BACKUP_DIR:
python scripts/rc5_cuda_handoff.py restore-check --manifest HANDOFF_MANIFEST.json --backup-dir BACKUP_DIR
python scripts/rc5_backup.py restore --from BACKUP_DIR --to RUN_DIR
```

`HANDOFF_MANIFEST.json` lists every candidate with the SHA256 of its official
`audio.flac`; `rc5_backup.py restore` re-hashes every restored file.

## 2. Official evaluator (frozen bundle, PRISTINE — no ROCm patch)

```bash
cd <parent of the pristine wsb_metrics bundle>
python wsb_eval.py prepare --metrics per --download huggingface --install
python wsb_eval.py score --input RUN_DIR/evaluation_inputs.jsonl --output RUN_DIR/scores_cuda --mode standard --metrics per
```

Do **not** set `WSB_ROCM_TORCH_OVERRIDE`. `standard` mode requires all 384 rows.

## 3. Compare

```bash
python scripts/rc5_cuda_handoff.py compare --rocm RUN_DIR/scores/per_song.jsonl \\
    --cuda RUN_DIR/scores_cuda/per_song.jsonl --out compare.json
```

## Expected run identity
SGLang `{m['run']['sglang_commit']}`, tracked diff
`{m['run']['sglang_tracked_diff_sha256']}`, YuE2-3B
`{str(m['run']['model_sha256'])[:16]}…`, VAE `{str(m['run']['vae_sha256'])[:16]}…`.
Return: `per_song.jsonl`, `protocol.json`, `per.environment.json` and a SHA256
list of the receipts. Transcripts stay with the owner; only the numeric
comparison belongs in the public evidence.
"""


# ----------------------------------------------------------- restore-check
def cmd_restore_check(a) -> int:
    m = json.loads(Path(a.manifest).read_text())
    bad, ok = [], 0
    for c in m["checkpoints"]:
        p = Path(a.backup_dir) / c["archive"]
        if not p.is_file():
            bad.append(f"{c['archive']}: missing")
        elif p.stat().st_size != c["bytes"] or sha_file(p) != c["sha256"]:
            bad.append(f"{c['archive']}: size/sha256 mismatch")
        else:
            ok += 1
    print(json.dumps({"ok": ok, "bad": bad, "passed": not bad and ok > 0}))
    return 0 if not bad and ok > 0 else 1


# ---------------------------------------------------------------- compare
def _sdi(ref: list, hyp: list) -> dict:
    n, mm = len(ref), len(hyp)
    d = [[0] * (mm + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(mm + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        ri = ref[i - 1]
        for j in range(1, mm + 1):
            c = 0 if ri == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
    s = dele = ins = 0
    i, j = n, mm
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            s += ref[i - 1] != hyp[j - 1]
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            dele += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return {"substitutions": s, "deletions": dele, "insertions": ins}


def _sel(row: dict):
    per = row["metrics"]["per"]
    rep = per["asr_repeats"][per["selected_asr_repeat"]]
    return (per["per"], per["edits"], abs(len(rep["phonemes"]) - per["reference_phonemes"]),
            row["candidate_index"])


def _boot(vals, reps=2000):
    rng = random.Random(20261124)
    xs = []
    for _ in range(reps):
        xs.append(sum(rng.choice(vals) for _ in range(len(vals))) / len(vals))
    xs.sort()
    return [round(xs[int(0.025 * reps)], 6), round(xs[int(0.975 * reps) - 1], 6)]


def cmd_compare(a) -> int:
    def load(p):
        rows = [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]
        return {r["id"]: r for r in rows}
    R, C = load(a.rocm), load(a.cuda)
    ids = sorted(set(R) & set(C))
    if not ids:
        print("no common candidate ids")
        return 2
    out_rows, by_prompt = [], {}
    same_sel = diff_sel = 0
    for cid in ids:
        r, c = R[cid]["metrics"]["per"], C[cid]["metrics"]["per"]
        if r.get("status") != "complete" or c.get("status") != "complete":
            out_rows.append({"id": cid, "status": "incomplete", "rocm": r.get("status"), "cuda": c.get("status")})
            continue
        rh = r["asr_repeats"][r["selected_asr_repeat"]]["phonemes"]
        ch = c["asr_repeats"][c["selected_asr_repeat"]]["phonemes"]
        row = {"id": cid, "prompt_index": R[cid]["prompt_index"], "lang": R[cid].get("lang"),
               "audio_sha256_identical": R[cid].get("audio_sha256") == C[cid].get("audio_sha256"),
               "reference_phonemes_identical": r["reference_phonemes"] == c["reference_phonemes"],
               "per_rocm": round(r["per"], 6), "per_cuda": round(c["per"], 6),
               "per_delta_pp": round((r["per"] - c["per"]) * 100, 4),
               "edits_rocm": r["edits"], "edits_cuda": c["edits"], "reference_phonemes": r["reference_phonemes"],
               "hyp_phonemes_rocm": len(rh), "hyp_phonemes_cuda": len(ch),
               "selected_transcript_identical": text_sha(r["asr_repeats"][r["selected_asr_repeat"]]["text"])
               == text_sha(c["asr_repeats"][c["selected_asr_repeat"]]["text"]),
               "sdi_rocm_vs_reference": _sdi(r["reference_tokens"], rh),
               "sdi_cuda_vs_reference": _sdi(c["reference_tokens"], ch),
               "empty_rocm": all(not x["text"].strip() for x in r["asr_repeats"]),
               "empty_cuda": all(not x["text"].strip() for x in c["asr_repeats"]),
               "truncated_rocm": r.get("truncated"), "truncated_cuda": c.get("truncated")}
        out_rows.append(row)
        by_prompt.setdefault(row["prompt_index"], []).append(row)
    ok = [x for x in out_rows if x.get("status") != "incomplete"]
    # official best-of-2 selection per prompt under each evaluator
    for p in sorted(by_prompt):
        rows = by_prompt[p]
        if len(rows) != 2:
            continue
        s_r = min(rows, key=lambda x: (x["per_rocm"], x["edits_rocm"],
                                       abs(x["hyp_phonemes_rocm"] - x["reference_phonemes"]),
                                       R[x["id"]]["candidate_index"]))["id"]
        s_c = min(rows, key=lambda x: (x["per_cuda"], x["edits_cuda"],
                                       abs(x["hyp_phonemes_cuda"] - x["reference_phonemes"]),
                                       C[x["id"]]["candidate_index"]))["id"]
        same_sel += s_r == s_c
        diff_sel += s_r != s_c
    def micro(key_per):
        e = sum(x["edits_" + key_per] for x in ok)
        n = sum(x["reference_phonemes"] for x in ok)
        return {"micro_per": round(e / n, 6) if n else None, "edits": e, "reference_phonemes": n}
    deltas = [x["per_delta_pp"] for x in ok]
    prompt_deltas = [sum(x["per_delta_pp"] for x in v) / len(v) for v in by_prompt.values()]
    summary = {
        "schema": "yue2-rc5-per-cuda-vs-rocm/1", "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rocm_source": str(a.rocm), "cuda_source": str(a.cuda),
        "rocm_per_song_sha256": sha_file(Path(a.rocm)), "cuda_per_song_sha256": sha_file(Path(a.cuda)),
        "candidates_compared": len(ok), "incomplete": len(out_rows) - len(ok),
        "all_audio_sha256_identical": all(x["audio_sha256_identical"] for x in ok),
        "all_reference_phonemes_identical": all(x["reference_phonemes_identical"] for x in ok),
        "rocm": {**micro("rocm"), "macro_per": round(sum(x["per_rocm"] for x in ok) / len(ok), 6) if ok else None,
                 "empty_transcripts": sum(x["empty_rocm"] for x in ok), "truncated": sum(1 for x in ok if x["truncated_rocm"])},
        "cuda": {**micro("cuda"), "macro_per": round(sum(x["per_cuda"] for x in ok) / len(ok), 6) if ok else None,
                 "empty_transcripts": sum(x["empty_cuda"] for x in ok), "truncated": sum(1 for x in ok if x["truncated_cuda"])},
        "micro_per_delta_pp_rocm_minus_cuda": round((micro("rocm")["edits"] / max(1, micro("rocm")["reference_phonemes"])
                                                     - micro("cuda")["edits"] / max(1, micro("cuda")["reference_phonemes"])) * 100, 4) if ok else None,
        "candidate_per_delta_pp_mean": round(sum(deltas) / len(deltas), 4) if deltas else None,
        "candidate_per_delta_pp_ci95": _boot(deltas) if deltas else None,
        "prompt_per_delta_pp_ci95": _boot(prompt_deltas) if prompt_deltas else None,
        "selected_transcripts_identical": sum(x["selected_transcript_identical"] for x in ok),
        "selection_agreement": {"same_candidate": same_sel, "different_candidate": diff_sel},
        "sdi_totals_rocm": {k: sum(x["sdi_rocm_vs_reference"][k] for x in ok) for k in ("substitutions", "deletions", "insertions")},
        "sdi_totals_cuda": {k: sum(x["sdi_cuda_vs_reference"][k] for x in ok) for k in ("substitutions", "deletions", "insertions")},
        "per_lang": {lang: {"n": sum(1 for x in ok if x["lang"] == lang),
                            "micro_per_rocm": round(sum(x["edits_rocm"] for x in ok if x["lang"] == lang) / max(1, sum(x["reference_phonemes"] for x in ok if x["lang"] == lang)), 6),
                            "micro_per_cuda": round(sum(x["edits_cuda"] for x in ok if x["lang"] == lang) / max(1, sum(x["reference_phonemes"] for x in ok if x["lang"] == lang)), 6)}
                     for lang in sorted({x["lang"] for x in ok})},
    }
    out = {"summary": summary, "rows": out_rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    public = {k: v for k, v in summary.items() if k not in ("rocm_source", "cuda_source")}
    print(json.dumps(public, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--evaluator-root", type=Path, default=Path("/data/yue2/benchmark/wsb_metrics"))
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(fn=cmd_pack)
    r = sub.add_parser("restore-check")
    r.add_argument("--manifest", type=Path, required=True)
    r.add_argument("--backup-dir", type=Path, required=True)
    r.set_defaults(fn=cmd_restore_check)
    c = sub.add_parser("compare")
    c.add_argument("--rocm", type=Path, required=True)
    c.add_argument("--cuda", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    c.set_defaults(fn=cmd_compare)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
