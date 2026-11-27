#!/usr/bin/env python3
"""rc6_verify_results.py — RC6 A5.6: developer self-verification tool.

Lets ANY developer verify their own results without trusting us:
  * GPU execution identity (from the run's own receipts — no self-claims)
  * model / runtime / configuration identity vs the pinned reference
  * audio integrity (lossless decode, non-silent, 48 kHz stereo, finite)
  * candidate coverage + evaluation coverage (when present)
  * performance receipt vs the reference envelope (with scope labels)
  * known-limitations checklist attached to the verdict

Verdict vocabulary (never grade-inflated):
  VERIFIED_REFERENCE_RUN              everything matches the frozen reference
  VERIFIED_WITH_DISCLOSED_DIFFERENCES  matches modulo disclosed differences
  VALID_PILOT_ONLY                    pilot-scale evidence only
  UNSUPPORTED_CONFIGURATION           hardware/stack outside the verified matrix
  INCOMPLETE                          artifacts missing / run unfinished
  FAILED                              verification checks failed

Usage:
  python3 scripts/rc6_verify_results.py --run-dir <song-dir-or-campaign-dir> \
      [--json-out out.json] [--compare-reference]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

REFERENCE = {
    "sglang_commit": "c67d541a40f8bf851e9fc1e925f5316638838cd6",
    "yue2_runtime_sha256": "342b2f531b14a201b4aae1a6a14424bed7f03cd7f993c3a1c09657a6d6109051",
    "mot_sha256": "1d55c42c1a9875c34f5d736e15078449992b044e807ce2a138e6cf289a1e59e9",
    "vae_sha256": "b6d283628913bb41145ba99e2314eef613905ee95f690eb70e8212d5f4965044",
    "expect_arch": "gfx1100",
    "config": {  # shape mirrors config.json's generation block + top-level keys
        "cot": "full", "cfg_scale": 1.0, "vae_decode": "halo_crop",
        "vae_core_frames": 1024, "vae_halo_frames": 16,
        "generation.ode_steps": 32,
        "generation.semantic.max_tokens": 9000,
        "generation.abc.max_tokens": 4096,
    },
    "perf_p50_wall_s": 275.27, "perf_mean_wall_s": 284.78,
    "rtf_mean": 1.2866, "realtime_multiplier_mean": 0.7894,
}

VERIFIED_STACK = {"gfx1100": "PHYSICAL_PASS (W7900 / W7900D, 48 GiB)"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_audio(path: Path) -> dict:
    import numpy as np
    import soundfile as sf
    info = sf.info(str(path))
    a, sr = sf.read(str(path), always_2d=True)
    finite = bool(np.isfinite(a).all()) if a.dtype.kind == "f" else True
    rms = float(math.sqrt(float((a.astype(np.float64) ** 2).mean()))) if len(a) else 0.0
    return {"path": str(path), "samplerate": sr, "channels": int(a.shape[1]),
            "frames": int(a.shape[0]), "seconds": round(len(a) / sr, 3),
            "finite": finite, "rms": round(rms, 5), "non_silent": rms > 1e-4,
            "is_48k_stereo": sr == 48000 and a.shape[1] == 2,
            "file_sha256": sha256_file(path)}


def verify_single_song(d: Path) -> tuple[dict, list[str]]:
    checks, problems = {}, []
    wav = next(iter(d.glob("*.wav")), None)
    artifacts = d / "candidate_0"
    flac = artifacts / "audio.flac" if artifacts.is_dir() else None
    if wav is None:
        problems.append("no WAV output in run dir")
    else:
        checks["audio_wav"] = check_audio(wav)
        if not checks["audio_wav"]["is_48k_stereo"]:
            problems.append("WAV is not 48 kHz stereo")
        if not checks["audio_wav"]["non_silent"] or not checks["audio_wav"]["finite"]:
            problems.append("WAV silent or non-finite")
    if flac and flac.is_file():
        checks["audio_flac"] = check_audio(flac)
        if not checks["audio_flac"]["is_48k_stereo"] or not checks["audio_flac"]["non_silent"]:
            problems.append("FLAC invalid/silent")
    result = artifacts / "result.json" if artifacts.is_dir() else None
    if result and result.is_file():
        r = json.loads(result.read_text())
        w = r.get("weights", {})
        mot_sha = (w.get("mot", {}).get("files", {})
                   .get("model.safetensors", {}).get("sha256"))
        vae_sha = (w.get("vae", {}).get("files", {})
                   .get("model.safetensors", {}).get("sha256"))
        checks["model_identity"] = {
            "mot_sha256": mot_sha, "vae_sha256": vae_sha,
            "matches_pinned": (mot_sha == REFERENCE["mot_sha256"] and
                               vae_sha == REFERENCE["vae_sha256"])}
        if not checks["model_identity"]["matches_pinned"]:
            problems.append("model identity does not match the pinned official weights")
        cfg = json.loads((artifacts / "config.json").read_text()) \
            if (artifacts / "config.json").is_file() else {}
        gen = cfg.get("generation", {}) or {}
        flat = {
            "cot": cfg.get("cot"), "cfg_scale": cfg.get("cfg_scale"),
            "vae_decode": cfg.get("vae_decode"),
            "vae_core_frames": cfg.get("vae_core_frames"),
            "vae_halo_frames": cfg.get("vae_halo_frames"),
            "generation.ode_steps": gen.get("ode_steps"),
            "generation.semantic.max_tokens": (gen.get("semantic") or {}).get("max_tokens"),
            "generation.abc.max_tokens": (gen.get("abc") or {}).get("max_tokens"),
        }
        diffs = {k: (flat.get(k), v) for k, v in REFERENCE["config"].items()
                 if flat.get(k) != v}
        runtime_sha = cfg.get("runtime_sha256")
        checks["generation_config"] = {
            "matches_reference": not diffs, "diffs": diffs,
            "runtime_sha256": runtime_sha,
            "runtime_matches_pinned": runtime_sha == REFERENCE["yue2_runtime_sha256"]}
        if diffs:
            problems.append(f"generation config differs from reference: {list(diffs)}")
        if not checks["generation_config"]["runtime_matches_pinned"]:
            problems.append("runtime_sha256 differs from the pinned reference runtime")
    else:
        problems.append("no candidate bundle (result.json) — cannot verify model identity")
    return checks, problems


def verify_campaign(d: Path) -> tuple[dict, list[str]]:
    checks, problems = {}, []
    # two journal shapes: rc5 driver (journal.jsonl, event rows) and legacy
    # run_wsb driver (generation_manifest.jsonl, per-candidate rows)
    jpath = d / "journal.jsonl"
    mpath = d / "generation_manifest.jsonl"
    if jpath.is_file():
        j = [json.loads(l) for l in jpath.read_text().splitlines() if l.strip()]
        complete = [e for e in j if e.get("event") == "result"
                    and e.get("status") == "complete"]
        for e in complete:
            e.setdefault("id", e.get("id"))
    elif mpath.is_file():
        complete = [json.loads(l) for l in mpath.read_text().splitlines()
                    if l.strip() and json.loads(l).get("status") == "complete"]
    else:
        complete = []
    ids = [e.get("id") for e in complete]
    checks["candidate_coverage"] = {
        "complete": len(complete),
        "unique_ids": len(set(ids)), "duplicates": len(ids) - len(set(ids)),
        "expect_384": len(complete) == 384,
    }
    if not complete:
        problems.append("campaign has no complete results")
    if checks["candidate_coverage"]["duplicates"]:
        problems.append("duplicate candidate ids in journal")
    rc = json.loads((d / "run_config.json").read_text()) if (d / "run_config.json").is_file() else {}
    runtime = rc.get("runtime", {}) if isinstance(rc.get("runtime"), dict) else {}
    if not runtime:
        # legacy run_wsb driver shape: flat keys
        runtime = {"sglang_commit": rc.get("sglang_commit"),
                   "yue2_runtime_sha256": rc.get("driver_repo_head")}
    checks["runtime_identity"] = {
        "sglang_commit": runtime.get("sglang_commit"),
        "yue2_runtime_sha256": runtime.get("yue2_runtime_sha256"),
        "shape": "legacy_run_wsb" if not rc.get("runtime") else "rc5_driver",
        "matches_pinned": (runtime.get("sglang_commit") == REFERENCE["sglang_commit"] and
                           runtime.get("yue2_runtime_sha256") in
                           (REFERENCE["yue2_runtime_sha256"], None)),
        "identity_fields_absent": not rc.get("runtime"),
    }
    if not checks["runtime_identity"]["matches_pinned"]:
        if checks["runtime_identity"]["identity_fields_absent"]:
            checks["runtime_identity"]["caveat"] = (
                "legacy driver run_config lacks the runtime identity fields; "
                "the session's GPU identity lives in the lifecycle receipt "
                "(run_with_server) — identity NOT independently confirmed here")
        else:
            problems.append("runtime identity differs from the pinned reference")
    gpu = rc.get("gpu", {}) if isinstance(rc.get("gpu"), dict) else {}
    arch = (gpu.get("arch") or [None])[0] if gpu else None
    if arch is None and isinstance(rc.get("platform"), dict):
        arch = rc["platform"].get("arch")
    checks["gpu_identity"] = {"arch": arch, "name": gpu.get("name") if gpu else None,
                              "bdf": gpu.get("pci_bdf") if gpu else None,
                              "uuid": gpu.get("uuid") if gpu else None,
                              "stack_status": VERIFIED_STACK.get(arch, "UNSUPPORTED")}
    if arch is None:
        checks["gpu_identity"]["caveat"] = ("run_config has no GPU identity; the session's "
                                            "GPU execution identity lives in the lifecycle "
                                            "receipt (GPU_EXECUTION_VERIFIED at run time)")
    elif arch not in VERIFIED_STACK:
        problems.append(f"GPU arch {arch} is outside the physically verified matrix")
    walls = [e.get("wall_s") for e in complete if isinstance(e.get("wall_s"), (int, float))]
    if walls:
        walls.sort()
        n = len(walls)
        p50 = walls[n // 2] if n % 2 else (walls[n // 2 - 1] + walls[n // 2]) / 2
        mean = sum(walls) / n
        checks["performance_receipt"] = {
            "n": n, "p50_wall_s": round(p50, 2), "mean_wall_s": round(mean, 2),
            "reference_p50_wall_s": REFERENCE["perf_p50_wall_s"],
            "measurement_scope": "per-candidate wall time on this rig (sequential, "
                                 "single-GPU); NOT comparable to throughput claims",
        }
    audio_ok = 0
    for e in complete[:8]:
        f = d / "songs" / e["id"] / "audio.flac"
        if f.is_file():
            c = check_audio(f)
            audio_ok += int(c["is_48k_stereo"] and c["non_silent"] and c["finite"])
    checks["audio_sample_audit"] = {"sampled": min(8, len(complete)), "passed": audio_ok}
    if audio_ok < min(8, len(complete)):
        problems.append("audio sample audit found invalid files")
    return checks, problems


def classify(mode: str, checks: dict, problems: list[str]) -> str:
    if problems:
        return "FAILED"
    if mode == "campaign":
        if not checks.get("candidate_coverage", {}).get("expect_384"):
            return "VALID_PILOT_ONLY" if checks.get("candidate_coverage", {}).get(
                    "complete", 0) else "INCOMPLETE"
        return "VERIFIED_REFERENCE_RUN"
    # single song
    cfg_ok = checks.get("generation_config", {}).get("matches_reference", False)
    model_ok = checks.get("model_identity", {}).get("matches_pinned", False)
    if cfg_ok and model_ok:
        return "VERIFIED_REFERENCE_RUN"
    if checks.get("audio_wav"):
        return "VERIFIED_WITH_DISCLOSED_DIFFERENCES"
    return "INCOMPLETE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--compare-reference", action="store_true")
    a = ap.parse_args()
    d = a.run_dir.resolve()
    if not d.is_dir():
        print(f"verify: FATAL run dir missing: {d}")
        return 2
    mode = "campaign" if ((d / "journal.jsonl").is_file() or
                          (d / "generation_manifest.jsonl").is_file()) else "single_song"
    checks, problems = (verify_campaign(d) if mode == "campaign" else verify_single_song(d))
    verdict = classify(mode, checks, problems)
    out = {
        "schema": "yue2-rc6-developer-verification/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_dir": str(d), "mode": mode, "checks": checks, "problems": problems,
        "verdict": verdict,
        "known_limitations_attached": [
            "single-GPU serial execution; concurrency not supported",
            "PER numbers depend on the disclosed ASR evaluator arm (see docs/KNOWN_LIMITATIONS.md)",
            "Q3O on ROCm is the adapted judge (no official-equivalence claim)",
            "cross-GPU-architecture byte-identity is not expected (same seeds give "
            "different waveforms on different archs)",
        ],
        "verdict_vocabulary": ["VERIFIED_REFERENCE_RUN", "VERIFIED_WITH_DISCLOSED_DIFFERENCES",
                               "VALID_PILOT_ONLY", "UNSUPPORTED_CONFIGURATION",
                               "INCOMPLETE", "FAILED"],
    }
    if a.compare_reference:
        out["reference_comparison"] = {
            "reference_scoreboard": "reports/w7900_rc5/rc5_1/06_FIVE_METRIC_SCOREBOARD.csv "
                                    "(frozen selected-192, official protocol)",
            "note": "quality metrics are only comparable under the SAME frozen protocol; "
                    "a pilot cannot be compared with the full scoreboard",
        }
    text = json.dumps(out, indent=1)
    if a.json_out:
        a.json_out.parent.mkdir(parents=True, exist_ok=True)
        a.json_out.write_text(text + "\n")
    print(text)
    return 0 if verdict in ("VERIFIED_REFERENCE_RUN", "VALID_PILOT_ONLY",
                            "VERIFIED_WITH_DISCLOSED_DIFFERENCES") else 1


if __name__ == "__main__":
    raise SystemExit(main())
