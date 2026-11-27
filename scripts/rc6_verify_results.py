#!/usr/bin/env python3
"""rc6_verify_results.py — RC6.1 M1: fail-closed, scope-labelled developer
self-verification tool.

RC6 defects V01-V10 closed here (see reports/developer_reference/rc6_1/
01_VERIFIER_RCA.md for the RED/GREEN evidence):

  V01 single song without a GPU lifecycle receipt can no longer reach any
      VERIFIED_* tier (the GPU execution layer is mandatory and binding).
  V02 bundle receipts are bound to actual content: every artifact hash in
      result.json is recomputed from the file on disk; a swapped audio file
      is FAILED, not VERIFIED.
  V03 WAV and FLAC must contain the SAME PCM (bit-exact md5 of decoded
      samples) — a valid-but-different FLAC is FAILED.
  V04 a journal row count alone never awards a full verdict: every complete
      row is audited (bundle present, artifacts hash-bound, seeds bound).
  V05 audio auditing covers ALL candidates by default; --quick produces
      SAMPLED_INTEGRITY_CHECK and can never award a full verdict.
  V06 missing GPU identity caps the verdict (scope.gpu_execution) instead
      of a caveat under a full VERIFIED.
  V07 runtime_sha256 None is a MISMATCH (fail-closed), never a match.
  V08 VERIFIED_REFERENCE_RUN requires evaluation coverage; generation-only
      full campaigns get the scope-limited VERIFIED_FULL_GENERATION.
  V09 only the official pilot shape (5 prompts x 2 = 10, indices
      0,1,2,79,81) is a pilot verdict; arbitrary counts are INCOMPLETE.
  V10 --compare-reference computes per-metric deltas (reference vs observed
      with coverage/eligibility labels) or reports NOT_PERFORMED explicitly.

Layered verification scope (a lower layer never implies a higher one):
  audio_integrity · gpu_execution · model_provenance · runtime_provenance ·
  generation_protocol · generation_coverage · evaluation_coverage ·
  scientific_reference

Verdict vocabulary (scope-qualified; legacy names kept as documented
aliases where they still exist):
  VERIFIED_FIRST_SONG               one song, full identity chain, first-song scope
  VERIFIED_BENCHMARK_PILOT          official 5x2 pilot + five-metric pilot scoring
  VERIFIED_FULL_GENERATION          384/384 campaign, no evaluation claim
  VERIFIED_FULL_BENCHMARK           384/384 + five-metric coverage
  VERIFIED_REFERENCE_RUN            full benchmark on the frozen reference protocol
  VALID_PILOT_ONLY                  legacy alias of the pilot-generation scope
  VERIFIED_WITH_DISCLOSED_DIFFERENCES  audio+identity verified, disclosed deltas
  SAMPLED_INTEGRITY_CHECK           --quick only; never a full verdict
  UNSUPPORTED_CONFIGURATION / INCOMPLETE / FAILED

Usage:
  python3 scripts/rc6_verify_results.py --run-dir <song-or-campaign> \
      [--json-out out.json] [--compare-reference] [--quick] \
      [--gpu-receipt path] [--expect-bdf 0000:03:00.0] \
      [--eval-receipts r1.json r2.json ...] [--model-root DIR]
Exit codes: 0 verified (any tier) · 1 FAILED/INCOMPLETE · 2 usage fatal.
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
    "config": {
        "cot": "full", "cfg_scale": 1.0, "vae_decode": "halo_crop",
        "vae_core_frames": 1024, "vae_halo_frames": 16,
        "generation.ode_steps": 32,
        "generation.semantic.max_tokens": 9000,
        "generation.abc.max_tokens": 4096,
    },
    "perf_p50_wall_s": 275.27, "perf_mean_wall_s": 284.78,
    "rtf_mean": 1.2866, "realtime_multiplier_mean": 0.7894,
}

# Official pilot protocol (frozen): 5 prompts x 2 candidates = 10
PILOT_PROMPT_INDICES = (0, 1, 2, 79, 81)
PILOT_EXPECTED_COUNT = 10
FULL_EXPECTED_COUNT = 384

VERIFIED_STACK = {"gfx1100": "PHYSICAL_PASS (W7900 / W7900D, 48 GiB)"}

VERDICT_VOCABULARY = [
    "VERIFIED_FIRST_SONG", "VERIFIED_BENCHMARK_PILOT", "VERIFIED_FULL_GENERATION",
    "VERIFIED_FULL_BENCHMARK", "VERIFIED_REFERENCE_RUN", "VALID_PILOT_ONLY",
    "VERIFIED_WITH_DISCLOSED_DIFFERENCES", "SAMPLED_INTEGRITY_CHECK",
    "UNSUPPORTED_CONFIGURATION", "INCOMPLETE", "FAILED",
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_SUBTYPE_DOMAIN = {"PCM_16": ("int16", 16), "PCM_24": ("int32", 24),
                   "PCM_32": ("int32", 32), "FLOAT": ("float32", None),
                   "DOUBLE": ("float64", None)}


def pcm_md5(path: Path) -> tuple[str, dict] | None:
    """Decode audio; the md5 is computed in the file's NATIVE integer domain
    (libsndfile's float32 conversion rounds differently for WAV vs FLAC, so
    float-domain md5s of the SAME content can differ)."""
    import numpy as np
    import soundfile as sf
    info = sf.info(str(path))
    dtype, bits = _SUBTYPE_DOMAIN.get(info.subtype, ("float32", None))
    a, sr = sf.read(str(path), always_2d=True, dtype=dtype)
    finite = bool(np.isfinite(a).all()) if a.dtype.kind == "f" else True
    rms = float(math.sqrt(float((a.astype(np.float64) ** 2).mean()))) if len(a) else 0.0
    chk = {"samplerate": sr, "channels": int(a.shape[1]), "frames": int(a.shape[0]),
           "seconds": round(len(a) / sr, 3), "finite": finite, "rms": round(rms, 6),
           "non_silent": rms > 1e-4, "is_48k_stereo": sr == 48000 and a.shape[1] == 2,
           "subtype": info.subtype, "pcm_bits": bits}
    return hashlib.md5(a.tobytes()).hexdigest(), chk


def pcm_compatible(wav_chk: dict, flac_chk: dict) -> bool:
    """V03 cross-check: WAV and FLAC carry the same samples, compared in the
    common integer domain (the finer file is shifted down to the coarser).
    The real pipeline is WAV PCM_16 + FLAC PCM_24 repack (lossless)."""
    if not (wav_chk.get("pcm_md5") and flac_chk.get("pcm_md5")):
        return False
    bw, bf = wav_chk.get("pcm_bits"), flac_chk.get("pcm_bits")
    if bw is None or bf is None:          # a float-domain file: exact md5 match
        return wav_chk["pcm_md5"] == flac_chk["pcm_md5"]
    if bw == bf:
        return wav_chk["pcm_md5"] == flac_chk["pcm_md5"]
    return False  # different bit depths: equality must be checked numerically


def pcm_equal(wav_path: Path, flac_path: Path) -> tuple[bool, str | None]:
    """Numerically compare two files in the coarser of their integer domains.

    libsndfile reads a PCM_24 FLAC as LEFT-justified int32 (value*2^31), so
    each file is first right-justified to its subtype bit depth, then the
    finer one is quantized down. The real pipeline (WAV PCM_16 repacked to
    FLAC PCM_24 by finalize) is exactly representable and must match."""
    import numpy as np
    import soundfile as sf
    iw, if_ = sf.info(str(wav_path)), sf.info(str(flac_path))
    dw, bw = _SUBTYPE_DOMAIN.get(iw.subtype, ("float32", None))
    df, bf = _SUBTYPE_DOMAIN.get(if_.subtype, ("float32", None))
    aw, _ = sf.read(str(wav_path), always_2d=True, dtype=dw)
    af, _ = sf.read(str(flac_path), always_2d=True, dtype=df)
    if aw.shape != af.shape:
        return False, f"frame/channel shape differs: {aw.shape} vs {af.shape}"
    if bw is None or bf is None:
        return bool(np.array_equal(aw.astype(np.float64), af.astype(np.float64))), None
    # right-justify to subtype bit depth (FLAC reads are left-justified)
    aw64 = aw.astype(np.int64)
    af64 = af.astype(np.int64)
    wav_left = iw.subtype.startswith("PCM") and dw == "int32" and bw < 32
    flac_left = if_.subtype.startswith("PCM") and df == "int32" and bf < 32
    if wav_left:
        aw64 >>= (32 - bw)
    if flac_left:
        af64 >>= (32 - bf)
    if bw == bf:
        return bool(np.array_equal(aw64, af64)), None
    fine, coarse, shift = (af64, aw64, bf - bw) if bf > bw else (aw64, af64, bw - bf)
    return bool(np.array_equal(fine >> shift, coarse)), None


def check_audio(path: Path) -> dict:
    r = pcm_md5(path)
    if r is None:
        return {"path": str(path), "decode_error": True}
    md5, chk = r
    out = {"path": str(path), **chk, "pcm_md5": md5, "file_sha256": sha256_file(path)}
    return out


# --------------------------------------------------------------- GPU receipt

GPU_RECEIPT_CANDIDATES = ("lifecycle-receipt.json",)


def find_gpu_receipt(d: Path, explicit: Path | None) -> tuple[Path | None, list[Path]]:
    """Search order: --gpu-receipt, run_dir, <run_dir>/../logs, ../../logs
    (the fresh-clone layout workspace/runs/<x> + workspace/logs)."""
    if explicit:
        return (explicit if explicit.is_file() else None), []
    tried = []
    for cand in (d / "lifecycle-receipt.json",
                 d.parent / "logs" / "lifecycle-receipt.json",
                 d.parent.parent / "logs" / "lifecycle-receipt.json"):
        tried.append(cand)
        if cand.is_file():
            return cand, tried
    return None, tried


def verify_gpu_receipt(receipt_path: Path, run: Path, expect_bdf: str | None) -> dict:
    """V01/V06 fix: bind the GPU lifecycle receipt to THIS run.

    Binding requirements (all must hold for VERIFIED):
      * receipt_type == gpu_lifecycle
      * steps contain gpu_identity with status GPU_EXECUTION_VERIFIED
      * BDF recorded and (if --expect-bdf given) equal
      * spawn session has pid + starttime
      * cleanup_state == CLEAN and no blocked processes
      * the executed cmd references THIS run's request.json (single-song) or
        the journal launch receipt lives inside the run (campaign)
    """
    scope = {"status": "NOT_VERIFIED", "receipt": str(receipt_path)}
    try:
        r = json.loads(receipt_path.read_text())
    except (OSError, ValueError) as e:
        scope["status"] = "FAILED"
        scope["error"] = f"unreadable receipt: {e}"
        return scope
    steps = {s.get("step"): s for s in r.get("steps", []) if isinstance(s, dict)}
    gi = steps.get("gpu_identity", {})
    scope["gpu_identity_status"] = gi.get("status")
    scope["bdf"] = gi.get("bdf")
    scope["uuid"] = (gi.get("device") or {}).get("unique_id") if isinstance(gi.get("device"), dict) else gi.get("uuid")
    spawn = r.get("spawn") or {}
    scope["session_pid"] = spawn.get("pid")
    scope["session_starttime"] = spawn.get("starttime")
    scope["cleanup_state"] = r.get("cleanup_state")
    cmd = r.get("cmd") or []
    req = run / "request.json"
    scope["cmd_references_run_request"] = any(
        str(req) in str(c) for c in cmd) if (req.is_file() and cmd) else None
    problems = []
    if r.get("receipt_type") != "gpu_lifecycle":
        problems.append("receipt_type is not gpu_lifecycle")
    if gi.get("status") != "GPU_EXECUTION_VERIFIED":
        problems.append(f"gpu_identity step status={gi.get('status')!r}")
    bdf = gi.get("bdf")
    if not bdf:
        problems.append("no PCI BDF recorded in the GPU identity step")
    elif expect_bdf and bdf != expect_bdf:
        problems.append(f"GPU BDF {bdf} != expected {expect_bdf}")
    if not (isinstance(spawn.get("pid"), int) and spawn.get("starttime")):
        problems.append("spawn session pid/starttime missing (no process identity)")
    if r.get("cleanup_state") != "CLEAN":
        problems.append(f"cleanup_state={r.get('cleanup_state')!r} (not CLEAN)")
    if r.get("blocked_processes"):
        problems.append("blocked processes recorded in the receipt")
    if req.is_file() and cmd and not scope["cmd_references_run_request"]:
        problems.append("lifecycle receipt command does not reference this run's request.json"
                        " (receipt not bound to THIS run)")
    scope["problems"] = problems
    scope["status"] = "VERIFIED" if not problems else "FAILED"
    return scope


def verify_campaign_gpu(run: Path, expect_bdf: str | None) -> dict:
    """Campaign GPU layer: lifecycle sessions under <run>/lifecycle/*, bound
    to the journal launch event when present."""
    scope = {"status": "NOT_VERIFIED"}
    lc = run / "lifecycle"
    sessions = sorted(p.name for p in lc.glob("*") if p.is_dir()) if lc.is_dir() else []
    scope["lifecycle_sessions"] = sessions
    if not sessions:
        # V06 fix: absence CAPS the verdict (identity chain incomplete);
        # it is not an outright failure — nothing failed, evidence is missing
        scope["problems"] = []
        return scope
    launch_receipts = []
    jpath = run / "journal.jsonl"
    if jpath.is_file():
        for line in jpath.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("event") == "launch":
                srv = e.get("server") or {}
                if srv.get("receipt"):
                    launch_receipts.append(srv["receipt"])
    scope["journal_launch_receipts"] = launch_receipts
    ok_sessions, problems = 0, []
    for s in sessions:
        rp = lc / s / "lifecycle-receipt.json"
        sub = verify_gpu_receipt(rp, run, expect_bdf) if rp.is_file() else \
            {"status": "FAILED", "problems": [f"missing {rp}"]}
        # campaign receipts run the driver, not the per-run request; the
        # cmd-binding check does not apply — the journal launch receipt
        # binding below does.
        sub_problems = [p for p in sub.get("problems", [])
                        if "request.json" not in p]
        if launch_receipts:
            inside = any(str(lc) in r for r in launch_receipts)
            if not inside:
                sub_problems.append("journal launch receipts are outside this run's lifecycle tree")
            for r in launch_receipts:
                rp2 = Path(r)
                if rp2.is_file() and launch_receipts and rp2 == rp:
                    pass
            # verify the sha of each launch receipt that exists
            for e_sha, rp2 in _launch_sha_pairs(jpath, lc):
                if rp2.is_file():
                    actual = sha256_file(rp2)
                    if actual != e_sha:
                        sub_problems.append(f"journal launch receipt sha mismatch: {rp2}")
        if not sub_problems and sub.get("status") in ("VERIFIED",):
            ok_sessions += 1
        else:
            problems.extend(f"{s}: {p}" for p in sub_problems or ["no valid receipt"])
    scope["verified_sessions"] = ok_sessions
    scope["problems"] = problems
    scope["status"] = "VERIFIED" if ok_sessions and not problems else "FAILED"
    return scope


def _launch_sha_pairs(jpath: Path, lc: Path) -> list[tuple[str, Path]]:
    out = []
    for line in jpath.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event") == "launch":
            srv = e.get("server") or {}
            if srv.get("receipt") and srv.get("receipt_sha256"):
                out.append((srv["receipt_sha256"], Path(srv["receipt"])))
    return out


# --------------------------------------------------------------- single song

def verify_single_song(d: Path, args) -> tuple[dict, list[str], dict, list[str]]:
    checks, problems, disclosures = {}, [], []
    scope = {}
    wav = next(iter(d.glob("*.wav")), None)
    artifacts = d / "candidate_0"
    flac = artifacts / "audio.flac" if artifacts.is_dir() else None
    wav_chk = None
    if wav is None:
        problems.append("no WAV output in run dir")
    else:
        try:
            wav_chk = check_audio(wav)
        except Exception as e:  # decode failure is a FAILED check, not a crash
            wav_chk = {"path": str(wav), "decode_error": True, "error": str(e)}
        checks["audio_wav"] = wav_chk
        if wav_chk.get("decode_error"):
            problems.append("WAV is not decodable")
        else:
            if not wav_chk["is_48k_stereo"]:
                problems.append("WAV is not 48 kHz stereo")
            if not wav_chk["non_silent"] or not wav_chk["finite"]:
                problems.append("WAV silent or non-finite")
    flac_chk = None
    if flac and flac.is_file():
        try:
            flac_chk = check_audio(flac)
        except Exception as e:
            flac_chk = {"path": str(flac), "decode_error": True, "error": str(e)}
        checks["audio_flac"] = flac_chk
        if flac_chk.get("decode_error"):
            problems.append("FLAC is not decodable")
        elif not flac_chk["is_48k_stereo"] or not flac_chk["non_silent"] or not flac_chk["finite"]:
            problems.append("FLAC invalid/silent/non-finite")
    # V03: WAV and FLAC must carry the SAME samples
    if wav_chk and flac_chk and not wav_chk.get("decode_error") and not flac_chk.get("decode_error"):
        equal, why = pcm_equal(wav, flac)
        if not equal:
            problems.append("WAV and FLAC PCM content DO NOT MATCH "
                            + (f"({why})" if why else ""))
    scope["audio_integrity"] = "VERIFIED" if not problems else "FAILED"

    # ---- bundle identity (V02: bind declared hashes to actual files) ----
    result = artifacts / "result.json" if artifacts.is_dir() else None
    if result and result.is_file():
        try:
            r = json.loads(result.read_text())
        except ValueError:
            r = None
            problems.append("candidate result.json is not valid JSON")
        if r is not None:
            if r.get("status") != "complete":
                problems.append(f"candidate result status={r.get('status')!r}")
            # artifact hash binding — recomputed from disk
            for name, meta in (r.get("artifacts") or {}).items():
                fp = artifacts / name
                declared = meta.get("sha256") if isinstance(meta, dict) else None
                if not fp.is_file():
                    problems.append(f"declared artifact missing on disk: {name}")
                elif declared is None or declared != sha256_file(fp):
                    problems.append(f"artifact hash mismatch (content not bound): {name}")
            w = r.get("weights", {})
            mot_sha = (w.get("mot", {}).get("files", {}).get("model.safetensors", {}).get("sha256"))
            vae_sha = (w.get("vae", {}).get("files", {}).get("model.safetensors", {}).get("sha256"))
            model_ok = mot_sha == REFERENCE["mot_sha256"] and vae_sha == REFERENCE["vae_sha256"]
            model_recomputed = False
            if args.model_root:
                mot_p = Path(args.model_root) / "YuE2-3B/model.safetensors"
                vae_p = Path(args.model_root) / "YuE2-Vae-legacy/model.safetensors"
                if mot_p.is_file() and vae_p.is_file():
                    model_ok = (sha256_file(mot_p) == REFERENCE["mot_sha256"] and
                                sha256_file(vae_p) == REFERENCE["vae_sha256"] and
                                mot_sha == REFERENCE["mot_sha256"] and vae_sha == REFERENCE["vae_sha256"])
                    model_recomputed = True
            checks["model_identity"] = {
                "mot_sha256": mot_sha, "vae_sha256": vae_sha,
                "matches_pinned": model_ok, "recomputed_from_disk": model_recomputed}
            scope["model_provenance"] = ("VERIFIED" if model_ok and model_recomputed else
                                         "VERIFIED_DECLARED" if model_ok else "MISMATCH")
            if not model_ok:
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
            runtime_ok = runtime_sha == REFERENCE["yue2_runtime_sha256"]  # V07: None != match
            checks["generation_config"] = {
                "matches_reference": not diffs, "diffs": diffs,
                "runtime_sha256": runtime_sha,
                "runtime_matches_pinned": runtime_ok}
            scope["runtime_provenance"] = "VERIFIED" if runtime_ok else \
                ("MISSING" if runtime_sha is None else "MISMATCH")
            scope["generation_protocol"] = "VERIFIED" if not diffs else "DIFFERENT"
            if diffs:
                disclosures.append(f"generation config differs from reference: {list(diffs)}")
            if not runtime_ok:
                problems.append("runtime_sha256 missing or differs from the pinned reference runtime")
    else:
        problems.append("no candidate bundle (result.json) — cannot verify model identity")
        scope["model_provenance"] = "NOT_PRESENT"
        scope["runtime_provenance"] = "NOT_PRESENT"
        scope["generation_protocol"] = "NOT_PRESENT"

    # ---- GPU execution layer (V01: no receipt = identity chain incomplete) ----
    rp, tried = find_gpu_receipt(d, args.gpu_receipt)
    checks["gpu_receipt_search"] = {"found": str(rp) if rp else None,
                                    "tried": [str(t) for t in tried]}
    if rp is None:
        scope["gpu_execution"] = "NOT_VERIFIED"
        disclosures.append("no GPU lifecycle receipt bound to this run "
                           "(pass --gpu-receipt if it lives elsewhere) — "
                           "GPU execution NOT verified; identity chain incomplete")
        checks["gpu_execution"] = scope["gpu_execution"]
    else:
        gi = verify_gpu_receipt(rp, d, args.expect_bdf)
        checks["gpu_execution"] = gi
        scope["gpu_execution"] = gi["status"]
        if gi["status"] != "VERIFIED":
            problems.extend(f"GPU receipt: {p}" for p in gi.get("problems", []))
    scope["generation_coverage"] = "VERIFIED_FIRST_SONG"
    scope["evaluation_coverage"] = "NOT_PRESENT"
    scope["scientific_reference"] = "NOT_ESTABLISHED"
    return checks, problems, scope, disclosures


def _id_pattern_ok(ids: list) -> tuple[bool, str | None]:
    """Official candidate-id shape: wsb_<3-digit prompt>_r{0,1}_s<seed>, each
    prompt exactly {0,1} (M1.4: fake 384-id coverage must not pass)."""
    import re
    pat = re.compile(r"^wsb_(\d{3})_r([01])_s(\d+)$")
    prompts: dict[str, set] = {}
    for cid in ids:
        m = pat.match(str(cid))
        if not m:
            return False, f"candidate id does not match the official shape: {cid}"
        prompts.setdefault(m.group(1), set()).add(m.group(2))
    bad = [p for p, v in prompts.items() if v != {"0", "1"}]
    if bad:
        return False, f"prompts without exactly two candidates r0/r1: {bad[:5]}"
    return True, None


def run_official_auditor(d: Path) -> dict | None:
    """M1.4: delegate to the proven official WSB auditor (manifest-seed
    fidelity, forged-bundle identity recompute, truncation policy). Returns
    None (with a reason) when the auditor cannot run, e.g. no workspace."""
    import os
    import subprocess
    ws = os.environ.get("YUE2_WORKSPACE", "/data/yue2")
    if not (Path(ws) / "benchmark" / "WildSongBench").is_dir():
        return {"status": "NOT_RUN", "reason": f"no WildSongBench workspace at {ws}"}
    cmd = [sys.executable, str(REPO / "scripts" / "verify_wsb_artifacts.py"),
           "--runs", str(d)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                           env={**os.environ, "YUE2_WORKSPACE": ws})
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"status": "NOT_RUN", "reason": f"auditor failed to execute: {e}"}
    try:
        out = json.loads(p.stdout)
    except ValueError:
        return {"status": "NOT_RUN", "reason": f"auditor output not JSON (rc={p.returncode})",
                "stderr": p.stderr[-400:]}
    out["status"] = "RAN"
    return out


# --------------------------------------------------------------- campaign

def _iter_complete_rows(d: Path) -> list[dict]:
    rows = []
    for p, key in ((d / "journal.jsonl", "journal"), (d / "generation_manifest.jsonl", "manifest")):
        if p.is_file():
            for line in p.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    e = None
                if e is None:
                    # fail-closed evidence: malformed journal lines are never
                    # silently skipped (a torn tail is an interrupted run,
                    # not a complete one)
                    rows.append({"__malformed__": True, "__raw__": line[:120]})
                    continue
                if key == "journal":
                    if e.get("event") == "result" and e.get("status") == "complete":
                        rows.append(e)
                elif e.get("status") == "complete":
                    rows.append(e)
            if rows:
                return rows
    return rows


def _song_dir(d: Path, cid: str) -> Path | None:
    for cand in (d / "songs" / cid, d / "songs" / cid / "candidate_0"):
        if (cand / "result.json").is_file() or (cand / "audio.flac").is_file():
            return cand
    return None


def verify_campaign(d: Path, args) -> tuple[dict, list[str], dict, list[str]]:
    checks, problems, disclosures = {}, [], []
    scope = {}
    complete = _iter_complete_rows(d)
    malformed = [r for r in complete if r.get("__malformed__")]
    complete = [r for r in complete if not r.get("__malformed__")]
    if malformed:
        problems.append(f"journal contains {len(malformed)} malformed line(s) "
                        "(fail-closed: an interrupted/tampered journal is not a complete run)")
    ids = [e.get("id") for e in complete]
    dup = len(ids) - len(set(ids))
    n = len(complete)
    checks["candidate_coverage"] = {
        "complete": n, "unique_ids": len(set(ids)), "duplicates": dup,
        "is_full_384": n == FULL_EXPECTED_COUNT,
        "is_official_pilot": _is_official_pilot(ids),
    }
    if not complete:
        problems.append("campaign has no complete results")
    if dup:
        problems.append("duplicate candidate ids in journal")
    unexpected = []
    songs_root = d / "songs"
    if songs_root.is_dir():
        known = set(ids)
        for p in songs_root.iterdir():
            if p.is_dir() and p.name not in known:
                unexpected.append(p.name)
    if unexpected:
        problems.append(f"unexpected candidate dirs not in the journal: {unexpected[:10]}")

    # V04/V05: audit EVERY complete row (or a bounded sample with --quick)
    rows_to_audit = complete if not args.quick else complete[:8]
    audio_fail, bundle_fail, seed_fail = [], [], []
    for e in rows_to_audit:
        cid = e.get("id")
        sdir = _song_dir(d, cid) if cid else None
        if sdir is None:
            bundle_fail.append(cid)
            continue
        flac = sdir / "audio.flac"
        if not flac.is_file():
            bundle_fail.append(cid)
            continue
        try:
            c = check_audio(flac)
        except Exception:
            c = {"decode_error": True}
        if c.get("decode_error") or not (c.get("is_48k_stereo") and c.get("non_silent")
                                         and c.get("finite")):
            audio_fail.append(cid)
        rj = sdir / "result.json"
        if rj.is_file():
            try:
                r = json.loads(rj.read_text())
            except ValueError:
                bundle_fail.append(cid)
                r = None
            if r:
                if r.get("status") != "complete":
                    bundle_fail.append(cid)
                for name, meta in (r.get("artifacts") or {}).items():
                    fp = sdir / name
                    if not fp.is_file() or not isinstance(meta, dict) or \
                            meta.get("sha256") != sha256_file(fp):
                        bundle_fail.append(cid)
                        break
        else:
            bundle_fail.append(cid)
        # seed binding: journal seed vs the bundle's request.json seed
        if isinstance(e.get("seed"), int):
            rq = sdir / "request.json"
            if rq.is_file():
                try:
                    q = json.loads(rq.read_text())
                    if q.get("seed") not in (e.get("seed"), None):
                        seed_fail.append(f"{cid}: request seed {q.get('seed')} != journal {e.get('seed')}")
                except ValueError:
                    seed_fail.append(f"{cid}: request.json unreadable")
    checks["artifact_audit"] = {
        "audited": len(rows_to_audit), "audio_invalid": sorted(set(audio_fail)),
        "bundle_invalid": sorted(set(bundle_fail)), "seed_binding_issues": seed_fail,
        "sampled_only": bool(args.quick),
    }
    for f in sorted(set(audio_fail)):
        problems.append(f"audio audit FAILED for candidate {f}")
    for f in sorted(set(bundle_fail)):
        problems.append(f"bundle audit FAILED for candidate {f} "
                        "(missing/unbound artifacts — journal row not backed by evidence)")
    problems.extend(seed_fail)

    scope["generation_coverage"] = ("VERIFIED_FULL_384" if n == FULL_EXPECTED_COUNT else
                                    "VERIFIED_OFFICIAL_PILOT" if _is_official_pilot(ids) else
                                    "INCOMPLETE")
    if args.quick:
        scope["generation_coverage"] = "SAMPLED_ONLY"

    # official id/prompt-candidate shape (cheap internal check; the official
    # auditor additionally verifies seeds against the frozen manifest)
    if n >= PILOT_EXPECTED_COUNT:
        ok_ids, why = _id_pattern_ok(ids)
        checks["candidate_id_shape"] = {"ok": ok_ids, "reason": why}
        if not ok_ids:
            problems.append(f"candidate id set is not the official shape: {why}")

    # ---- runtime identity (V07: None never matches) ----
    rc = json.loads((d / "run_config.json").read_text()) if (d / "run_config.json").is_file() else {}
    runtime = rc.get("runtime", {}) if isinstance(rc.get("runtime"), dict) else {}
    if not runtime:
        runtime = {"sglang_commit": rc.get("sglang_commit"),
                   "yue2_runtime_sha256": rc.get("driver_repo_head")}
    sgl_ok = runtime.get("sglang_commit") == REFERENCE["sglang_commit"]
    rt_ok = runtime.get("yue2_runtime_sha256") == REFERENCE["yue2_runtime_sha256"]
    checks["runtime_identity"] = {
        "sglang_commit": runtime.get("sglang_commit"),
        "yue2_runtime_sha256": runtime.get("yue2_runtime_sha256"),
        "shape": "legacy_run_wsb" if not rc.get("runtime") else "rc5_driver",
        "matches_pinned": sgl_ok and rt_ok,
    }
    scope["runtime_provenance"] = "VERIFIED" if (sgl_ok and rt_ok) else "MISMATCH"
    if not sgl_ok:
        problems.append("sglang commit differs from the pinned reference")
    if not rt_ok:
        problems.append("runtime_sha256 missing or differs from the pinned reference "
                        "(legacy runs: bind the lifecycle/runtime receipts explicitly)")

    # model provenance: declared per-row + optional one-shot recompute
    mot_ok = n > 0
    for e in (complete[:1] if complete else []):
        sdir = _song_dir(d, e.get("id")) if e.get("id") else None
        rj = sdir / "result.json" if sdir else None
        if rj and rj.is_file():
            r = json.loads(rj.read_text())
            w = r.get("weights", {})
            mot_ok = ((w.get("mot", {}).get("files", {}).get("model.safetensors", {}).get("sha256")
                       == REFERENCE["mot_sha256"]) and
                      (w.get("vae", {}).get("files", {}).get("model.safetensors", {}).get("sha256")
                       == REFERENCE["vae_sha256"]))
    model_recomputed = False
    if args.model_root:
        mot_p = Path(args.model_root) / "YuE2-3B/model.safetensors"
        vae_p = Path(args.model_root) / "YuE2-Vae-legacy/model.safetensors"
        if mot_p.is_file() and vae_p.is_file():
            mot_ok = (sha256_file(mot_p) == REFERENCE["mot_sha256"] and
                      sha256_file(vae_p) == REFERENCE["vae_sha256"] and mot_ok)
            model_recomputed = True
    checks["model_identity"] = {"matches_pinned": bool(mot_ok and n),
                                "recomputed_from_disk": model_recomputed,
                                "basis": "first complete row + (optional) model-root recompute"}
    scope["model_provenance"] = "VERIFIED" if (mot_ok and n) else "MISMATCH"
    if not (mot_ok and n):
        problems.append("model identity not established for the campaign rows")

    scope["generation_protocol"] = "VERIFIED" if not problems else "DIFFERENT"

    # ---- GPU execution (V06) ----
    gi = verify_campaign_gpu(d, args.expect_bdf)
    checks["gpu_execution"] = gi
    scope["gpu_execution"] = gi["status"]
    if gi["status"] != "VERIFIED":
        problems.extend(f"campaign GPU: {p}" for p in gi.get("problems", []))

    # ---- gpu arch in run_config (kept: UNSUPPORTED matrix) ----
    gpu = rc.get("gpu", {}) if isinstance(rc.get("gpu"), dict) else {}
    arch = (gpu.get("arch") or [None])[0] if gpu else None
    if arch is None and isinstance(rc.get("platform"), dict):
        arch = rc["platform"].get("arch")
    checks["gpu_identity"] = {"arch": arch, "name": gpu.get("name") if gpu else None,
                              "bdf": gpu.get("pci_bdf") if gpu else None,
                              "uuid": gpu.get("uuid") if gpu else None,
                              "stack_status": VERIFIED_STACK.get(arch, "UNSUPPORTED")}
    if arch is not None and arch not in VERIFIED_STACK:
        problems.append(f"GPU arch {arch} is outside the physically verified matrix")

    walls = [e.get("wall_s") for e in complete if isinstance(e.get("wall_s"), (int, float))]
    if walls:
        walls.sort()
        m = len(walls)
        p50 = walls[m // 2] if m % 2 else (walls[m // 2 - 1] + walls[m // 2]) / 2
        checks["performance_receipt"] = {
            "n": m, "p50_wall_s": round(p50, 2), "mean_wall_s": round(sum(walls) / m, 2),
            "reference_p50_wall_s": REFERENCE["perf_p50_wall_s"],
            "measurement_scope": "per-candidate wall time on this rig (sequential, single-GPU)",
        }

    # ---- evaluation coverage (V08: missing metrics scope-cap the verdict,
    # they do not fail a generation-only campaign; inconsistency does) ----
    ev = verify_evaluation_coverage(d, args.eval_receipts or [])
    checks["evaluation_coverage"] = ev
    scope["evaluation_coverage"] = ev["status"]

    scope["scientific_reference"] = ("VERIFIED" if scope["evaluation_coverage"] == "VERIFIED_FIVE_METRIC"
                                     and scope["generation_coverage"] == "VERIFIED_FULL_384" else
                                     "NOT_ESTABLISHED")

    # ---- official WSB auditor (M1.4: manifest-seed fidelity, forged-bundle
    # identity recompute, truncation policy — delegated, not reimplemented) ----
    if not args.quick:
        aud = run_official_auditor(d)
        if aud is not None:
            checks["official_wsb_audit"] = {
                "status": aud.get("status"), "verdict": aud.get("verdict"),
                "problems": aud.get("problems"), "reason": aud.get("reason")}
            if aud.get("status") == "RAN":
                if aud.get("verdict") not in ("FULL", "PILOT"):
                    problems.append(f"official WSB auditor verdict={aud.get('verdict')!r}")
                elif aud.get("problems"):
                    problems.append(f"official WSB auditor reported {len(aud['problems'])} problems")
            else:
                disclosures.append("official WSB auditor not runnable: "
                                   f"{aud.get('reason')} — manifest-seed fidelity and "
                                   "forged-bundle recompute NOT independently confirmed; "
                                   "scientific_reference capped")
                scope["scientific_reference"] = "NOT_ESTABLISHED"
    return checks, problems, scope, disclosures


def _is_official_pilot(ids: list) -> bool:
    if len(ids) != PILOT_EXPECTED_COUNT or len(set(ids)) != PILOT_EXPECTED_COUNT:
        return False
    prompts = {}
    for cid in ids:
        parts = str(cid).split("_")
        if len(parts) < 3:
            return False
        try:
            p, r = int(parts[1]), int(parts[2][1:])
        except (ValueError, IndexError):
            return False
        prompts.setdefault(p, set()).add(r)
    if set(prompts) != set(PILOT_PROMPT_INDICES):
        return False
    return all(v == {0, 1} for v in prompts.values())


# ----------------------------------------------------- evaluation coverage

METRIC_KEYS = ("songbench", "per", "mulan", "allmusiccaps", "q3o")


def _summarize_group(summary: dict) -> dict[str, dict]:
    """Extract per-metric {scored, expected, complete, mean} from the wsb
    summary schema. Metrics may live at groups.all (unified/pilot format) or
    under standard_selected/selected_candidates.groups.all (campaign layout:
    the SELECTED arm is the scoreboard-relevant one)."""
    out: dict[str, dict] = {}
    roots = []
    for key in ("", "standard_selected", "selected_candidates", "unselected_candidates"):
        node = summary if not key else summary.get(key)
        if isinstance(node, dict):
            g = (node.get("groups") or {}).get("all")
            if isinstance(g, dict):
                roots.append(g)
    for groups in roots:
        for metric, node in groups.items():
            if not (isinstance(node, dict) and "scored" in node):
                continue
            kk = metric.lower()
            if kk not in METRIC_KEYS and kk != "per":
                continue
            means = node.get("means") or {}
            mean = means.get("Global Avg")
            if mean is None and kk == "per":
                mean = node.get("per_micro")
            if mean is None:
                mean = means.get(metric)
            if mean is not None and kk not in out:
                out[kk] = {"scored": node.get("scored"), "expected": node.get("expected"),
                           "complete": node.get("complete"), "mean": mean}
    return out


def verify_evaluation_coverage(d: Path, extra_receipts: list[Path]) -> dict:
    """Five-metric coverage from run-dir scoring summaries and/or explicit
    --eval-receipts JSONs (rc5_1 report formats supported)."""
    found: dict[str, dict] = {}
    sources: dict[str, str] = {}
    # 1) unified pilot/five-metric summary
    for cand in (d / "scoring" / "summary.json", d / "scoring_summary.json"):
        if cand.is_file():
            try:
                s = json.loads(cand.read_text())
            except ValueError:
                continue
            fm = s.get("five_metric") or s.get("metrics")
            if isinstance(fm, dict):
                for k, v in fm.items():
                    kk = k.lower()
                    if kk in METRIC_KEYS and isinstance(v, (int, float)):
                        cov = (s.get("coverage") or {}).get(kk)
                        found.setdefault(kk, {"mean": float(v), "scored": cov})
                        sources.setdefault(kk, str(cand))
    # 2) run-dir campaign layouts
    layouts = ((d / "per_full" / "summary.json", "per"),
               (d / "songbench_sel" / "summary.json", "songbench"),
               (d / "additional_sel" / "summary.json", None),
               (d / "mulan_sel" / "summary.json", None),
               (d / "amc_sel" / "summary.json", None))
    for path, _ in layouts:
        if path.is_file():
            try:
                s = json.loads(path.read_text())
            except ValueError:
                continue
            for k, v in _summarize_group(s).items():
                if k in METRIC_KEYS and k not in found:
                    found[k] = v
                    sources[k] = str(path)
    # additional_sel may embed mulan/allmusiccaps under its own groups
    add = d / "additional_sel" / "summary.json"
    if add.is_file():
        try:
            s = json.loads(add.read_text())
            for k, v in _summarize_group(s).items():
                if k in METRIC_KEYS and k not in found:
                    found[k], sources[k] = v, str(add)
        except ValueError:
            pass
    # 3) explicit receipt files (rc5_1 report schema: value + coverage)
    for p in extra_receipts:
        try:
            s = json.loads(Path(p).read_text())
        except (OSError, ValueError):
            continue
        schema = str(s.get("schema", ""))
        if "q3o" in schema and "mean" not in found.get("q3o", {}):
            v = (s.get("score") or {}).get("q3o_mean_0_5")
            cov = (s.get("coverage") or {}).get("evaluated")
            if v is not None:
                found["q3o"] = {"mean": v, "scored": cov}
                sources["q3o"] = str(p)
        for key in ("mulan", "allmusiccaps"):
            if key in schema and key not in found and s.get("value") is not None:
                found[key] = {"mean": s["value"],
                              "scored": (s.get("coverage") or {}).get("scored")}
                sources[key] = str(p)
        if "per" in schema and "per" not in found and s.get("value") is not None:
            found["per"] = {"mean": s["value"], "scored": (s.get("coverage") or {}).get("scored")}
            sources["per"] = str(p)
        if "songbench" in schema and "songbench" not in found and s.get("value") is not None:
            found["songbench"] = {"mean": s["value"], "scored": (s.get("coverage") or {}).get("scored")}
            sources["songbench"] = str(p)
    missing = [k for k in METRIC_KEYS if k not in found]
    complete = {k: bool(v.get("complete", v.get("scored") not in (None, 0)))
                for k, v in found.items()}
    status = ("VERIFIED_FIVE_METRIC" if not missing and all(complete.values()) else
              "PARTIAL" if found else "NOT_PRESENT")
    return {"status": status, "metrics": found, "sources": sources,
            "missing": missing, "complete": complete,
            "note": "all five metrics must be scored over the SAME selection "
                    "for a benchmark verdict; cross-arm mixing is forbidden"}


# --------------------------------------------------------------- compare

def _reference_scoreboard() -> dict[str, dict]:
    """Prefer the RC6.1 five-metric scoreboard (paper + A + B arms); fall
    back to the frozen rc5_1 scoreboard (Scoreboard A)."""
    import csv
    paths = [REPO / "reports/developer_reference/rc6_1/04_FIVE_METRIC_SCOREBOARDS.csv",
             REPO / "reports/w7900_rc5/rc5_1/06_FIVE_METRIC_SCOREBOARD.csv"]
    for p in paths:
        if not p.is_file():
            continue
        ref = {}
        with p.open() as f:
            for row in csv.DictReader(f):
                name = (row.get("metric") or "").lower()
                key = next((k for k in METRIC_KEYS if k in name), None)
                if key:
                    ref[key] = {"metric": row.get("metric"),
                                "reference_value": _num(row.get("rc5_1_w7900") or row.get("scoreboard_A") or row.get("paper")),
                                "paper_value": _num(row.get("paper")),
                                "comparability": row.get("comparability")}
        if ref:
            return {"path": str(p), "metrics": ref}
    return {"path": None, "metrics": {}}


def _num(v):
    if v is None:
        return None
    try:
        s = str(v).strip().rstrip("%")
        return float(s)
    except ValueError:
        return None


def compare_reference(out_metrics: dict | None, run_dir: Path) -> dict:
    ref = _reference_scoreboard()
    if not out_metrics:
        return {"status": "NOT_PERFORMED",
                "reason": "no user metric scoreboard found for this run "
                          "(expected <run-dir>/scoring/summary.json with five_metric, "
                          "or pass --eval-receipts)",
                "reference_scoreboard": ref["path"]}
    rows = {}
    for k, r in ref["metrics"].items():
        obs = out_metrics.get(k, {})
        ov = obs.get("mean")
        rv = r.get("reference_value")
        row = {"metric": r.get("metric"), "reference_value": rv,
               "reference_arm": "scoreboard_A (frozen transformers selection S_T)" ,
               "observed_value": ov,
               "coverage": obs.get("scored"),
               "comparability": r.get("comparability")}
        if rv is not None and ov is not None:
            row["absolute_delta"] = round(ov - rv, 6)
            row["relative_delta"] = (round((ov - rv) / rv, 6) if rv else None)
            if k == "per":
                row["unit"] = "percentage points" if max(ov, rv) > 1 else "ratio"
        else:
            row["absolute_delta"] = None
            row["relative_delta"] = None
        rows[k] = row
    return {"status": "COMPUTED", "reference_scoreboard": ref["path"],
            "metrics": rows,
            "eligibility": "a pilot-scale observation is NOT a like-for-like "
                            "comparison with the full selected-192 scoreboard; "
                            "deltas are diagnostic only",
            "protocol_differences": "PER depends on the disclosed ASR evaluator "
                                    "arm; Q3O on ROCm is the adapted judge"}


# --------------------------------------------------------------- classify

def classify(mode: str, checks: dict, problems: list[str], scope: dict,
             quick: bool, disclosures: list[str]) -> str:
    if quick:
        return "SAMPLED_INTEGRITY_CHECK" if not problems else "FAILED"
    if problems:
        return "FAILED"
    if mode == "single_song":
        if scope.get("audio_integrity") != "VERIFIED":
            return "INCOMPLETE"
        # identity chain: model + runtime + GPU execution must ALL be present
        identity_ok = (scope.get("model_provenance") in ("VERIFIED", "VERIFIED_DECLARED")
                       and scope.get("runtime_provenance") == "VERIFIED"
                       and scope.get("gpu_execution") == "VERIFIED")
        if not identity_ok:
            return "INCOMPLETE"          # broken identity chain is never a VERIFIED tier
        if disclosures:
            return "VERIFIED_WITH_DISCLOSED_DIFFERENCES"
        return "VERIFIED_FIRST_SONG"
    # campaign
    gcov = scope.get("generation_coverage")
    gpu_ok = scope.get("gpu_execution") == "VERIFIED"
    if gcov == "VERIFIED_FULL_384":
        if not gpu_ok:
            return "INCOMPLETE"        # generation evidence present, GPU chain missing
        if scope.get("evaluation_coverage") == "VERIFIED_FIVE_METRIC":
            if scope.get("scientific_reference") == "VERIFIED" and not disclosures:
                return "VERIFIED_REFERENCE_RUN"
            return "VERIFIED_FULL_BENCHMARK"
        return "VERIFIED_FULL_GENERATION"
    if gcov == "VERIFIED_OFFICIAL_PILOT":
        if not gpu_ok:
            return "INCOMPLETE"
        if scope.get("evaluation_coverage") == "VERIFIED_FIVE_METRIC":
            return "VERIFIED_BENCHMARK_PILOT"
        return "VALID_PILOT_ONLY"
    return "INCOMPLETE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--compare-reference", action="store_true")
    ap.add_argument("--quick", action="store_true",
                    help="sampled audit only — verdict is SAMPLED_INTEGRITY_CHECK, "
                         "never a full campaign PASS")
    ap.add_argument("--gpu-receipt", type=Path, default=None)
    ap.add_argument("--expect-bdf", default=None,
                    help="require the GPU receipt to record this exact PCI BDF")
    ap.add_argument("--eval-receipts", type=Path, nargs="*", default=[],
                    help="evaluation receipt JSONs (rc5_1 report formats)")
    ap.add_argument("--model-root", type=Path, default=None,
                    help="workspace models root for one-shot weight recompute")
    a = ap.parse_args()
    d = a.run_dir.resolve()
    if not d.is_dir():
        print(f"verify: FATAL run dir missing: {d}")
        return 2
    mode = "campaign" if ((d / "journal.jsonl").is_file() or
                          (d / "generation_manifest.jsonl").is_file()) else "single_song"
    if mode == "campaign":
        checks, problems, scope, disclosures = verify_campaign(d, a)
    else:
        checks, problems, scope, disclosures = verify_single_song(d, a)
    verdict = classify(mode, checks, problems, scope, a.quick, disclosures)
    out = {
        "schema": "yue2-rc6_1-developer-verification/2",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_dir": str(d), "mode": mode, "checks": checks, "problems": problems,
        "disclosed_differences": disclosures,
        "verdict": verdict,
        "verification_scope": scope,
        "sampled_only": bool(a.quick),
        "known_limitations_attached": [
            "single-GPU serial execution; concurrency not supported",
            "PER numbers depend on the disclosed ASR evaluator arm (see docs/KNOWN_LIMITATIONS.md)",
            "Q3O on ROCm is the adapted judge (no official-equivalence claim)",
            "cross-GPU-architecture byte-identity is not expected",
            "verdicts are scope-labelled: a single song can never award a campaign verdict",
        ],
        "verdict_vocabulary": VERDICT_VOCABULARY,
    }
    if a.compare_reference:
        user_metrics = None
        sc = d / "scoring" / "summary.json"
        if sc.is_file():
            try:
                s = json.loads(sc.read_text())
                fm = s.get("five_metric") or s.get("metrics")
                if isinstance(fm, dict):
                    user_metrics = {k: {"mean": v, "scored": (s.get("coverage") or {}).get(k)}
                                    for k, v in fm.items() if isinstance(v, (int, float))}
            except ValueError:
                pass
        if user_metrics is None:
            ev = checks.get("evaluation_coverage") or {}
            user_metrics = ev.get("metrics") or None
        out["reference_comparison"] = compare_reference(user_metrics, d)
    text = json.dumps(out, indent=1)
    if a.json_out:
        a.json_out.parent.mkdir(parents=True, exist_ok=True)
        a.json_out.write_text(text + "\n")
    print(text)
    return 0 if verdict in ("VERIFIED_FIRST_SONG", "VERIFIED_BENCHMARK_PILOT",
                            "VERIFIED_FULL_GENERATION", "VERIFIED_FULL_BENCHMARK",
                            "VERIFIED_REFERENCE_RUN", "VALID_PILOT_ONLY",
                            "VERIFIED_WITH_DISCLOSED_DIFFERENCES",
                            "SAMPLED_INTEGRITY_CHECK") else 1


if __name__ == "__main__":
    raise SystemExit(main())
