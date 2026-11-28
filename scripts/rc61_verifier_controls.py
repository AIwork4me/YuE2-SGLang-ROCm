#!/usr/bin/env python3
"""rc61_verifier_controls.py — M1.7 negative controls for the developer
verifier.

For each control: build a synthetic fixture, run the CURRENT verifier CLI as
a subprocess (real exit code), and also run the RC6 verifier (extracted from
the frozen commit eeb2115 via git) against the same fixture to record the
RED (pre-fix) behaviour. Produces
reports/developer_reference/rc6_1/01_VERIFIER_NEGATIVE_CONTROLS.json.

Every fixture is synthetic (tiny sine waves); no frozen evidence is touched.

Usage:  python3 scripts/rc61_verifier_controls.py
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "reports/developer_reference/rc6_1/01_VERIFIER_NEGATIVE_CONTROLS.json"
RC6_SHA = "eeb2115fb5411c12ff7de415c1cb8a61702b7700"
SR = 48000

sys.path.insert(0, str(Path(__file__).resolve().parent))
REF = json.loads(subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, 'scripts'); import rc6_verify_results as V;"
     "import json; print(json.dumps(V.REFERENCE))"],
    capture_output=True, text=True, cwd=str(REPO)).stdout)


def sine(freq=440.0, seconds=0.5):
    t = np.linspace(0.0, seconds, int(SR * seconds), endpoint=False)
    return np.stack([0.3 * np.sin(2 * math.pi * freq * t)] * 2, axis=1).astype(np.float32)


def sha(p: Path):
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make_song(run: Path, *, flac_pcm=None, artifact_hash=None, weights=None,
              runtime_sha="auto", wav_flac_repack=True, gpu_receipt_kwargs=None,
              with_receipt=True, extra=None):
    run.mkdir(parents=True, exist_ok=True)
    (run / "candidate_0").mkdir(exist_ok=True)
    sf.write(str(run / "song.wav"), sine(), SR, subtype="PCM_16")
    if wav_flac_repack:
        aw, _ = sf.read(str(run / "song.wav"), always_2d=True, dtype="int16")
        sf.write(str(run / "candidate_0" / "audio.flac"), aw, SR, subtype="PCM_24")
    else:
        sf.write(str(run / "candidate_0" / "audio.flac"),
                 flac_pcm if flac_pcm is not None else sine(freq=880.0), SR, subtype="PCM_24")
    af = run / "candidate_0" / "audio.flac"
    declared = sha(af) if artifact_hash is None else artifact_hash
    mot = REF["mot_sha256"] if weights is None else weights
    vae = REF["vae_sha256"] if weights is None else weights
    (run / "candidate_0" / "result.json").write_text(json.dumps({
        "status": "complete", "identity": "i" * 64, "truncated": False,
        "sample_rate": SR, "audio_seconds": 0.5,
        "weights": {"mot": {"files": {"model.safetensors": {"sha256": mot, "bytes": 1}}},
                    "vae": {"files": {"model.safetensors": {"sha256": vae, "bytes": 1}}}},
        "artifacts": {"audio.flac": {"sha256": declared}}}))
    (run / "candidate_0" / "config.json").write_text(json.dumps({
        "cot": "full", "cfg_scale": 1.0, "vae_decode": "halo_crop",
        "vae_core_frames": 1024, "vae_halo_frames": 16,
        "generation": {"ode_steps": 32, "semantic": {"max_tokens": 9000},
                       "abc": {"max_tokens": 4096}},
        "runtime_sha256": REF["yue2_runtime_sha256"] if runtime_sha == "auto" else runtime_sha}))
    (run / "request.json").write_text(json.dumps({"seed": 831001}))
    if with_receipt:
        rk = gpu_receipt_kwargs or {}
        (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run, **rk)))
    if extra:
        extra(run)
    return run


def gpu_receipt(run: Path, *, bdf="0000:03:00.0", request_path=None, status="GPU_EXECUTION_VERIFIED"):
    return {"receipt_type": "gpu_lifecycle", "who": "nc",
            "cmd": ["curl", "--data-binary",
                    f"@{request_path or (run / 'request.json')}"],
            "spawn": {"pid": 99, "starttime": "7", "session": 99},
            "server_exit": 0, "cmd_rc": 0, "cleanup_state": "CLEAN",
            "blocked_processes": [],
            "steps": [{"step": "gpu_identity", "status": status, "bdf": bdf,
                       "gpu_execution": "VERIFIED", "rc": 0}]}


def make_camp(root: Path, ids, *, song_dirs=None, gpu=True, runtime_sha="auto",
              journal_suffix="", dup_ids=None, run_config_extra=None):
    d = root
    d.mkdir(parents=True, exist_ok=True)
    rows = [{"event": "result", "id": cid, "status": "complete",
             "seed": 831001 + i, "wall_s": 10.0} for i, cid in enumerate(ids)]
    seed_of = {r["id"]: r["seed"] for r in rows}
    if dup_ids:
        rows += [{"event": "result", "id": cid, "status": "complete",
                  "seed": 1, "wall_s": 10.0} for cid in dup_ids]
    (d / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + journal_suffix)
    (d / "run_config.json").write_text(json.dumps({
        "run_id": "nc", "runtime": {"sglang_commit": REF["sglang_commit"],
                                    "yue2_runtime_sha256":
                                        REF["yue2_runtime_sha256"] if runtime_sha == "auto"
                                        else runtime_sha},
        "gpu": {"arch": ["gfx1100"], "name": "AMD Radeon Pro W7900D",
                "pci_bdf": "0000:03:00.0", "uuid": "e9d0e20bb686e6c6"}}))
    (d / "songs").mkdir(exist_ok=True)
    n = len(ids) if song_dirs is None else song_dirs
    for cid in ids[:n]:
        cdir = d / "songs" / cid
        cdir.mkdir(parents=True, exist_ok=True)
        sf.write(str(cdir / "audio.flac"), sine(), SR, subtype="PCM_24")
        (cdir / "result.json").write_text(json.dumps({
            "status": "complete", "identity": "i" * 64,
            "weights": {"mot": {"files": {"model.safetensors": {"sha256": REF["mot_sha256"]}}},
                        "vae": {"files": {"model.safetensors": {"sha256": REF["vae_sha256"]}}}},
            "artifacts": {"audio.flac": {"sha256": sha(cdir / "audio.flac")}}}))
        (cdir / "config.json").write_text(json.dumps(
            {"runtime_sha256": REF["yue2_runtime_sha256"]}))
        (cdir / "request.json").write_text(json.dumps({"seed": seed_of.get(cid, 831001)}))
    if gpu:
        (d / "lifecycle" / "s1" / "rws_gpu_identity").mkdir(parents=True, exist_ok=True)
        (d / "lifecycle" / "s1" / "lifecycle-receipt.json").write_text(json.dumps({
            "receipt_type": "gpu_lifecycle", "cleanup_state": "CLEAN",
            "spawn": {"pid": 7, "starttime": "9", "session": 7},
            "server_exit": 0, "cmd_rc": 0,
            "steps": [{"step": "gpu_identity", "status": "GPU_EXECUTION_VERIFIED",
                       "bdf": "0000:03:00.0", "gpu_execution": "VERIFIED"}]}))
    if run_config_extra:
        rc = json.loads((d / "run_config.json").read_text())
        rc.update(run_config_extra)
        (d / "run_config.json").write_text(json.dumps(rc))
    return d


PILOT_IDS = [f"wsb_{p:03d}_r{j}_s{831000+p*2+j}" for p in (0, 1, 2, 79, 81) for j in (0, 1)]
FULL384_IDS = [f"wsb_{p:03d}_r{j}_s{831000+p*2+j}" for p in range(192) for j in (0, 1)]


def run_cli(verifier: Path, run_dir: Path, *extra) -> tuple[str | None, int]:
    p = subprocess.run([sys.executable, str(verifier), "--run-dir", str(run_dir)]
                       + [str(e) for e in extra], capture_output=True, text=True,
                       timeout=300)
    try:
        return json.loads(p.stdout)["verdict"], p.returncode
    except (ValueError, KeyError):
        return None, p.returncode


def main() -> int:
    old = Path(tempfile.mkdtemp(prefix="rc6_verifier_")) / "rc6_verify_results.py"
    got = subprocess.run(["git", "show", f"{RC6_SHA}:scripts/rc6_verify_results.py"],
                         capture_output=True, cwd=str(REPO))
    if got.returncode != 0:
        print(f"FATAL: cannot extract RC6 verifier from {RC6_SHA}")
        return 2
    old.write_text(got.stdout.decode())
    new = REPO / "scripts/rc6_verify_results.py"

    controls = []

    def add(name, defect, fixture, expected, extra=()):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run = fixture(root)
            old_v, old_rc = run_cli(old, run, *extra)
            new_v, new_rc = run_cli(new, run, *extra)
        controls.append({
            "control": name, "defect": defect,
            "reproducer": f"synthetic fixture; verifier CLI subprocess (see {Path(__file__).name})",
            "expected": expected,
            "rc6_verdict": old_v, "rc6_exit": old_rc,
            "rc6_1_verdict": new_v, "rc6_1_exit": new_rc,
            "detected": new_v == expected,
            "regression_of_defect": (old_v == expected) is False,
        })

    add("NC01 missing GPU receipt (V01)",
        "single song, all identity fields match, no GPU lifecycle receipt",
        lambda r: make_song(r / "song", with_receipt=False),
        "INCOMPLETE")
    add("NC02 GPU receipt from another run (V01/A02)",
        "receipt cmd references a different request.json",
        lambda r: make_song(r / "song", gpu_receipt_kwargs={
            "request_path": str(r / "other.json")}),
        "FAILED")
    add("NC03 wrong GPU BDF (V06)",
        "receipt records a different PCI BDF than --expect-bdf",
        lambda r: make_song(r / "song", gpu_receipt_kwargs={"bdf": "0000:23:00.0"}),
        "FAILED", ("--expect-bdf", "0000:03:00.0"))
    add("NC04 wrong model SHA (A03)",
        "result.json declares non-pinned weights",
        lambda r: make_song(r / "song", weights="e" * 64),
        "FAILED")
    add("NC05 missing runtime SHA (V07)",
        "config.json has runtime_sha256: null",
        lambda r: make_song(r / "song", runtime_sha=None),
        "FAILED")
    add("NC06 wrong runtime SHA (A04)",
        "config.json declares a different runtime_sha256",
        lambda r: make_song(r / "song", runtime_sha="e" * 64),
        "FAILED")
    add("NC07 audio replaced, stale artifact hash (V02)",
        "FLAC swapped; result.json keeps the old hash",
        lambda r: make_song(r / "song", flac_pcm=sine(freq=880.0), wav_flac_repack=False,
                            artifact_hash=None),
        "FAILED")
    add("NC08 WAV/FLAC content mismatch (V03)",
        "valid FLAC with different PCM than the WAV",
        lambda r: make_song(r / "song", wav_flac_repack=False, flac_pcm=sine(freq=880.0)),
        "FAILED")
    add("NC09 audio corruption beyond sampled prefix (V05/A07)",
        "10-candidate campaign, candidates 9-10 silent/mono",
        lambda r: _corrupt_tail(r),
        "FAILED")
    add("NC10 journal count without bundles (V04)",
        "384 complete journal rows, only 8 bundles",
        lambda r: make_camp(r / "camp", FULL384_IDS, song_dirs=8),
        "FAILED")
    add("NC11 duplicate candidate ids (A15)",
        "pilot journal with one duplicated id",
        lambda r: make_camp(r / "camp", PILOT_IDS, dup_ids=[PILOT_IDS[0]]),
        "FAILED")
    add("NC12 fake 384-id coverage (A08)",
        "384 rows whose ids are not the official shape",
        lambda r: make_camp(r / "camp", [f"fake_{i:03d}_r{i%2}_s{i}" for i in range(384)],
                            song_dirs=8),
        "FAILED")
    add("NC13 truncated run presented as full",
        "382 complete rows (one full prompt missing)",
        lambda r: make_camp(r / "camp", FULL384_IDS[:382], song_dirs=382),
        "INCOMPLETE")
    add("NC14 malformed journal line (A16)",
        "pilot journal plus a torn JSON line",
        lambda r: make_camp(r / "camp", PILOT_IDS,
                            journal_suffix='{"event": "result", "id": "broken\n'),
        "FAILED")
    add("NC15 missing song bundle for a journal row",
        "one journal row has no songs/<id> directory",
        lambda r: make_camp(r / "camp", PILOT_IDS, song_dirs=9),
        "FAILED")
    add("NC16 campaign GPU identity missing (V06)",
        "campaign without lifecycle receipts",
        lambda r: make_camp(r / "camp", PILOT_IDS, gpu=False),
        "INCOMPLETE")
    add("NC17 campaign runtime SHA None (V07)",
        "run_config runtime.yue2_runtime_sha256 null",
        lambda r: make_camp(r / "camp", PILOT_IDS, runtime_sha=None),
        "FAILED")
    add("NC18 arbitrary complete count as pilot (V09)",
        "3 complete rows presented as a pilot",
        lambda r: make_camp(r / "camp", FULL384_IDS[:3], song_dirs=3),
        "INCOMPLETE")
    add("NC19 quick mode cannot award full (V05)",
        "10-candidate campaign audited with --quick",
        lambda r: make_camp(r / "camp", PILOT_IDS),
        "SAMPLED_INTEGRITY_CHECK", ("--quick",))
    add("NC20 valid official pilot (positive control)",
        "official 5x2 pilot shape, all bundles valid",
        lambda r: make_camp(r / "camp", PILOT_IDS),
        "VALID_PILOT_ONLY")
    add("NC21 valid first song (positive control)",
        "single song with the full identity chain",
        lambda r: make_song(r / "song"),
        "VERIFIED_FIRST_SONG")
    add("NC22 full generation without evaluation (V08)",
        "384 bundles, no metric receipts",
        lambda r: make_camp(r / "camp", FULL384_IDS),
        "VERIFIED_FULL_GENERATION")

    out = {
        "schema": "yue2-rc6_1-verifier-negative-controls/1",
        "verifier": "scripts/rc6_verify_results.py",
        "rc6_baseline_verifier_sha": RC6_SHA,
        "fixtures": "synthetic (tiny sine waves); no frozen evidence touched",
        "note": "rc6_verdict column = the pre-fix behaviour reproduced live from the "
                "frozen commit (RED evidence); rc6_1_verdict = post-fix (GREEN)",
        "controls": controls,
        "summary": {
            "total": len(controls),
            "detected": sum(c["detected"] for c in controls),
            "defects_reproduced_in_rc6": sum(1 for c in controls if c["regression_of_defect"]),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(out["summary"]))
    return 0 if all(c["detected"] for c in controls) else 1


def _corrupt_tail(root: Path) -> Path:
    d = make_camp(root / "camp", PILOT_IDS)
    for cid in PILOT_IDS[8:]:
        sf.write(str(d / "songs" / cid / "audio.flac"),
                 np.zeros((SR // 10, 1), dtype=np.float32), SR // 10, subtype="PCM_16")
    return d


if __name__ == "__main__":
    raise SystemExit(main())
