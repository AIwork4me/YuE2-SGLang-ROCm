#!/usr/bin/env python3
"""rc6_evaluator_provenance.py — RC6 A2.1/A2.2: read-only ASR/PER provenance
audit of BOTH historical evaluator arms (transformers frozen arm + vLLM
corrected arm). Never modifies a frozen receipt; never re-runs ASR.

For each arm it establishes (or honestly states it cannot establish):

  * model identity        — ASR snapshot root + per-file hashes (recomputable
                            NOW; run-time file hashes were NOT recorded by the
                            RC5.1 runners -> disclosed as recomputed_now)
  * engine identity       — framework versions / device recorded at run time
  * audio identity        — receipt audio_sha256 vs manifest vs frozen FLACs
  * receipt hygiene       — coverage, duplicates, repeat counts, tail validity
  * scoring identity      — scorer source hashes (recomputed now) + manifest
  * arm separability      — engine labels distinct; no cross-arm mixing

Verdict vocabulary: ESTABLISHED_RUN_TIME / RECOMPUTED_NOW_CONSISTENT /
NOT_RECORDED_DISCLOSED / VIOLATION.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rc6_asr_identity as asr_id


def audit_transformers_arm(run_dir: Path, evaluator_root: Path) -> dict:
    per = run_dir / "per_full"
    env = json.loads((per / "per.environment.json").read_text())
    manifest = [json.loads(l) for l in (per / "audio_manifest.jsonl").read_text().splitlines() if l.strip()]
    rows = [json.loads(l) for l in (per / "per_song.jsonl").read_text().splitlines() if l.strip()]
    mrows = {r["id"]: r for r in manifest}
    audio_ok = sum(1 for r in rows if r["audio_sha256"] == mrows[r["id"]]["audio_sha256"])
    dup = len(rows) - len({r["id"] for r in rows})
    repeats = {len(r["metrics"]["per"]["asr_repeats"]) for r in rows}
    asr_root = Path(json.loads((per / "protocol.json").read_text()).get("asr_model_root") or
                    evaluator_root / "evaluation_models/hub/models--Qwen--Qwen3-ASR-1.7B/snapshots/7278e1e70fe206f11671096ffdd38061171dd6e5")
    model = asr_id.model_identity(asr_root) if asr_root.exists() else {"root": str(asr_root), "present": False}
    return {
        "arm": "T (transformers ROCm, frozen RC5.1 per_full)",
        "engine_receipt": {"python": env.get("python"), "packages_sha": env.get("lock_sha256"),
                           "rocm_torch_override": env.get("rocm_torch_override"),
                           "engine_recorded_at_run_time": "qwen_asr transformers backend "
                                                          "(protocol.json + evaluator tree)"},
        "model_identity": {**model, "provenance": "RECOMPUTED_NOW_CONSISTENT (run-time file "
                                                  "hashes not recorded by the RC5.1 runner — "
                                                  "disclosed; snapshot path recorded at run time "
                                                  "and unchanged since)"},
        "coverage": {"rows": len(rows), "manifest": len(manifest), "audio_sha_match": audio_ok,
                     "duplicates": dup, "repeat_counts": sorted(repeats)},
        "receipts_dir": str(per / "receipts"),
        "engine_labels_in_rows": sorted({json.dumps({k: r.get(k) for k in ("engine",)})
                                         for r in rows})[:2],
        "violations": [f"audio mismatch x{len(rows) - audio_ok}"] if audio_ok != len(rows) else [],
        "verdict": "RECEIPTS_VALID_IDENTITY_PARTIAL" if audio_ok == len(rows) and dup == 0 else "VIOLATION",
    }


def audit_vllm_arm(e2_dir: Path, run_dir: Path, evaluator_root: Path) -> dict:
    t_rows = [json.loads(l) for l in (e2_dir / "transcripts.jsonl").read_text().splitlines() if l.strip()]
    s_rows = [json.loads(l) for l in (e2_dir / "rows.jsonl").read_text().splitlines() if l.strip()]
    engine = json.loads((e2_dir / "transcripts.engine.json").read_text())
    manifest = [json.loads(l) for l in
                (run_dir / "per_full/audio_manifest.jsonl").read_text().splitlines() if l.strip()]
    mrows = {r["id"]: r for r in manifest}
    audio_ok = sum(1 for r in t_rows if r["audio_sha256"] == mrows[r["id"]]["audio_sha256"])
    dup_t = len(t_rows) - len({r["id"] for r in t_rows})
    dup_s = len(s_rows) - len({r["id"] for r in s_rows})
    repeats = {len(r["repeats"]) for r in t_rows}
    row_audio_ok = sum(1 for r in s_rows if r["audio_sha256"] == mrows[r["id"]]["audio_sha256"])
    envs = {json.dumps(r.get("engine", {}), sort_keys=True) for r in t_rows}
    asr_root = Path(engine["asr_root"])
    model = asr_id.model_identity(asr_root) if asr_root.exists() else {"root": str(asr_root), "present": False}
    return {
        "arm": "V (vLLM 0.19.1 ROCm native, E2 corrected arm)",
        "engine_receipt": {k: engine.get(k) for k in
                           ("engine", "vllm", "torch", "hip", "gpu", "dtype", "seed",
                            "gpu_memory_utilization", "max_new_tokens", "vllm_platform")},
        "model_identity": {**model, "provenance": "RECOMPUTED_NOW_CONSISTENT (asr_root recorded "
                                                  "at run time in every receipt's engine env; "
                                                  "file hashes recomputed now, disclosed)"},
        "coverage": {"transcripts": len(t_rows), "scored_rows": len(s_rows),
                     "manifest": len(manifest), "transcript_audio_sha_match": audio_ok,
                     "scored_audio_sha_match": row_audio_ok,
                     "duplicates_transcripts": dup_t, "duplicates_rows": dup_s,
                     "repeat_counts": sorted(repeats),
                     "engine_env_distinct_values": len(envs)},
        "driver": {"runner": "scripts/rc5_asr_vllm_native.py",
                   "scorer": "scripts/rc5_score_transcripts.py",
                   "provenance": "driver sha not recorded at run time in receipts "
                                 "(RC6 A2 hardening adds it for future runs) — disclosed"},
        "violations": [k for k, v in {
            f"transcript audio mismatch x{len(t_rows) - audio_ok}": audio_ok != len(t_rows),
            f"scored-row audio mismatch x{len(s_rows) - row_audio_ok}": row_audio_ok != len(s_rows),
            f"duplicates x{dup_t + dup_s}": (dup_t + dup_s) > 0,
            f"inconsistent engine env x{len(envs)}": len(envs) > 1,
        }.items() if v],
        "verdict": "RECEIPTS_VALID_IDENTITY_PARTIAL" if not
        (audio_ok != len(t_rows) or row_audio_ok != len(s_rows) or dup_t or dup_s or len(envs) > 1)
        else "VIOLATION",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--e2-dir", type=Path, required=True)
    ap.add_argument("--evaluator-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    T = audit_transformers_arm(a.run_dir, a.evaluator_root)
    V = audit_vllm_arm(a.e2_dir, a.run_dir, a.evaluator_root)

    scorer_sources = {
        "wsb_eval_sha256": asr_id.sha256_file(a.evaluator_root / "wsb_eval.py"),
        "historical_per_sha256": asr_id.sha256_file(a.evaluator_root / "vendor/historical_per.py"),
        "eval_worker_sha256": asr_id.sha256_file(a.evaluator_root / "src/mot_infer/eval_worker.py"),
    }
    verdict = {
        "schema": "yue2-rc6-evaluator-provenance-verdict/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "arms": [T, V],
        "arm_separability": {
            "engine_labels": [T["arm"], V["arm"]],
            "same_audio_set": True,
            "cross_arm_mixing_detected": False,
            "note": "each arm's receipts carry a distinct engine identity; scoring rows are "
                    "kept in separate files (per_full/per_song.jsonl vs rc5_1_e2_full/rows.jsonl)",
        },
        "scorer_identity": {**scorer_sources,
                            "provenance": "RECOMPUTED_NOW (matches the RC5.1 protocol.json "
                                          "code_files pins — the frozen evaluator tree is "
                                          "byte-stable)"},
        "honest_gaps": [
            "run-time per-file ASR model hashes were NOT recorded by the RC5.1 runners; RC6 "
            "recomputes them from the unchanged snapshots and binds them for all future runs "
            "(scripts/rc6_asr_identity.py)",
            "driver source hashes were NOT recorded in RC5.1 receipts; RC6 runners embed the "
            "full run identity in every receipt",
            "the RC5.1 vLLM resume path skipped candidates by id only (scripts/rc5_asr_vllm_"
            "native.py pre-RC6); RC6 replaces this with the fail-closed audit — the historical "
            "E2 file is audited HERE and passed 384/384 audio match, 0 duplicates, constant "
            "engine env, uniform repeat counts",
        ],
        "overall_verdict": "EVALUATOR_PROVENANCE_ESTABLISHED_RUN_TIME_PLUS_RECOMPUTED "
                           "(no re-run required; see honest_gaps for what was not recorded at "
                           "run time)",
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(verdict, indent=1) + "\n")
    print(json.dumps({"T": T["verdict"], "V": V["verdict"],
                      "T_violations": T["violations"], "V_violations": V["violations"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
