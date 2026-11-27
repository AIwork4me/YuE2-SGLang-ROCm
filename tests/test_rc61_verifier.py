#!/usr/bin/env python3
"""RED tests for RC6.1 M1 — V01..V10 false-VERIFIED paths of the developer
verifier (scripts/rc6_verify_results.py).

Every test encodes the DESIRED fail-closed behaviour. Against the RC6
verifier (commit eeb2115) these tests FAIL — that is the RED evidence
(reproducing V01-V10). After the RC6.1 fix they must all pass (GREEN).
Fixture runs are fully synthetic (tiny 48 kHz stereo sine waves) — no models,
no GPU, no real evidence is touched.

Run:  python3 -m pytest tests/test_rc61_verifier.py -v
"""
from __future__ import annotations

import json
import math
import sys
import wave
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rc6_verify_results as V  # noqa: E402


SR = 48000
REFERENCE = V.REFERENCE


def sine_pcm(seconds: float = 0.5, freq: float = 440.0) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(SR * seconds), endpoint=False)
    sig = 0.3 * np.sin(2 * math.pi * freq * t)
    return np.stack([sig, sig], axis=1).astype(np.float32)


def write_song_files(run: Path, pcm: np.ndarray, flac_pcm: np.ndarray | None = None):
    # mirror the real pipeline: WAV PCM_16 first, then the FLAC repacked FROM
    # the WAV's int16 content (lossless n*256 as PCM_24)
    sf.write(str(run / "song.wav"), pcm, SR, subtype="PCM_16")
    if flac_pcm is None:
        aw, _ = sf.read(str(run / "song.wav"), always_2d=True, dtype="int16")
        sf.write(str(run / "candidate_0" / "audio.flac"), aw, SR, subtype="PCM_24")
    else:
        sf.write(str(run / "candidate_0" / "audio.flac"), flac_pcm, SR, subtype="PCM_24")


def sha(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make_bundle(run: Path, *, audio_ok: bool = True, wav_flac_same: bool = True,
                artifact_hash_matches: bool = True, runtime_sha: str | None = "auto",
                weights_ok: bool = True, config_ok: bool = True) -> Path:
    """A synthetic single-song bundle whose identity fields all match the
    pinned reference (unless a knob disables one)."""
    run.mkdir(parents=True, exist_ok=True)
    (run / "candidate_0").mkdir(exist_ok=True)
    pcm = sine_pcm()
    other = sine_pcm(seconds=0.5, freq=880.0)
    write_song_files(run, pcm, None if wav_flac_same else other)
    artifacts = {"audio.flac": {"sha256": sha(run / "candidate_0" / "audio.flac")
                                if artifact_hash_matches else "0" * 64}}
    mot = REFERENCE["mot_sha256"] if weights_ok else "e" * 64
    vae = REFERENCE["vae_sha256"] if weights_ok else "e" * 64
    (run / "candidate_0" / "result.json").write_text(json.dumps({
        "status": "complete", "identity": "i" * 64, "truncated": False,
        "sample_rate": SR, "audio_seconds": 0.5,
        "weights": {"mot": {"files": {"model.safetensors": {"sha256": mot, "bytes": 1}}},
                    "vae": {"files": {"model.safetensors": {"sha256": vae, "bytes": 1}}}},
        "artifacts": artifacts,
    }))
    cfg = {"cot": "full", "cfg_scale": 1.0, "vae_decode": "halo_crop",
           "vae_core_frames": 1024, "vae_halo_frames": 16,
           "generation": {"ode_steps": 32,
                          "semantic": {"max_tokens": 9000},
                          "abc": {"max_tokens": 4096}},
           "runtime_sha256": (REFERENCE["yue2_runtime_sha256"]
                              if runtime_sha == "auto" else runtime_sha)}
    (run / "candidate_0" / "config.json").write_text(json.dumps(cfg))
    (run / "request.json").write_text(json.dumps({"seed": 831001, "lyrics": "x", "style": "y"}))
    return run


def gpu_receipt(run: Path, *, bdf: str = "0000:03:00.0", status="GPU_EXECUTION_VERIFIED",
                request_path: str | None = None, cleanup="CLEAN", session_pid=4242):
    return {
        "receipt_type": "gpu_lifecycle", "who": "test-lifecycle",
        "cmd": ["curl", "-sS", "-X", "POST", "http://127.0.0.1:31000/v1/audio/generations",
                "--data-binary", f"@{request_path or (run / 'request.json')}"],
        "spawn": {"pid": session_pid, "starttime": "12345", "session": session_pid},
        "server_exit": 0, "cmd_rc": 0, "cleanup_state": cleanup, "blocked_processes": [],
        "steps": [
            {"step": "gpu_identity", "status": status, "bdf": bdf, "gpu_execution": "VERIFIED", "rc": 0},
            {"step": "launch_server", "status": "LAUNCHED", "pid": session_pid},
            {"step": "stop_server", "status": "STOPPED", "rc": 0},
        ],
    }


def run_verify(run: Path, *extra: str) -> tuple[dict, int]:
    """Run the verifier CLI in-process; return (output-json, exit-code)."""
    import contextlib
    import io
    argv = ["rc6_verify_results.py", "--run-dir", str(run)] + [str(e) for e in extra]
    buf = io.StringIO()
    old = sys.argv
    try:
        sys.argv = argv
        with contextlib.redirect_stdout(buf):
            rc = V.main()
    finally:
        sys.argv = old
    return json.loads(buf.getvalue()), rc


# ---------------------------------------------------------------- V01
def test_V01_single_song_without_gpu_receipt_cannot_get_high_verdict(tmp_path):
    run = make_bundle(tmp_path / "song")
    out, rc = run_verify(run)
    assert out["verdict"] not in ("VERIFIED_REFERENCE_RUN", "VERIFIED_FIRST_SONG",
                                  "VERIFIED_WITH_DISCLOSED_DIFFERENCES"), out
    scope = out.get("verification_scope", {})
    assert scope.get("gpu_execution") != "VERIFIED"


def test_V01b_single_song_with_gpu_receipt_gets_scoped_first_song_verdict(tmp_path):
    run = make_bundle(tmp_path / "song")
    (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run)))
    out, rc = run_verify(run)
    assert out["verdict"] == "VERIFIED_FIRST_SONG", out
    scope = out["verification_scope"]
    assert scope["gpu_execution"] == "VERIFIED"
    assert scope["model_provenance"] in ("VERIFIED", "VERIFIED_DECLARED")
    assert scope["runtime_provenance"] == "VERIFIED"


# ---------------------------------------------------------------- V02
def test_V02_audio_content_not_bound_to_bundle_receipt(tmp_path):
    run = make_bundle(tmp_path / "song")          # result.json has the ORIGINAL hash
    sf.write(str(run / "candidate_0" / "audio.flac"), sine_pcm(freq=880.0), SR, subtype="PCM_16")
    (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run)))
    out, rc = run_verify(run)
    assert out["verdict"] == "FAILED", out
    assert rc == 1


# ---------------------------------------------------------------- V03
def test_V03_wav_flac_content_mismatch(tmp_path):
    run = make_bundle(tmp_path / "song", wav_flac_same=False,
                      artifact_hash_matches=True)
    # keep the artifact hash correct for the (different) flac so only the
    # WAV/FLAC cross-check can catch it
    (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run)))
    out, rc = run_verify(run)
    assert out["verdict"] == "FAILED", out
    assert any("WAV" in p and "FLAC" in p for p in out.get("problems", [])), out


# ---------------------------------------------------------------- V07
def test_V07_missing_runtime_sha_is_not_a_match(tmp_path):
    run = make_bundle(tmp_path / "song", runtime_sha=None)
    (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run)))
    out, rc = run_verify(run)
    assert out["verdict"] != "VERIFIED_FIRST_SONG", out
    assert out["verification_scope"]["runtime_provenance"] != "VERIFIED"


# ---------------------------------------------------------------- campaign
def make_campaign(root: Path, *, n: int, song_dirs: int, gpu_ok: bool = True,
                  runtime_sha: str | None = "auto", corrupt_from: int | None = None,
                  extra_row_ids: list[str] | None = None, ids=None) -> Path:
    d = root / "camp"
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    ids = ids or [f"wsb_{i:03d}_r{j}_s{831000+i*2+j}" for i in range(n) for j in (0, 1)]
    for i, cid in enumerate(ids[:n]):
        rows.append({"event": "result", "id": cid, "status": "complete",
                     "seed": 831000 + i, "wall_s": 10.0})
    (d / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    rt = {"sglang_commit": REFERENCE["sglang_commit"],
          "yue2_runtime_sha256": (REFERENCE["yue2_runtime_sha256"]
                                  if runtime_sha == "auto" else runtime_sha)}
    (d / "run_config.json").write_text(json.dumps({
        "run_id": "testcamp", "runtime": rt,
        "gpu": {"arch": ["gfx1100"], "name": "AMD Radeon Pro W7900D",
                "pci_bdf": "0000:03:00.0", "uuid": "e9d0e20bb686e6c6"}}))
    (d / "songs").mkdir(exist_ok=True)
    for i, cid in enumerate(ids[:song_dirs]):
        cdir = d / "songs" / cid          # campaign layout: artifacts directly under songs/<id>
        cdir.mkdir(parents=True, exist_ok=True)
        if corrupt_from is not None and i >= corrupt_from:
            sf.write(str(cdir / "audio.flac"), np.zeros((SR // 10, 1), dtype=np.float32),
                     SR // 10, subtype="PCM_16")  # silent + mono + wrong rate
        else:
            sf.write(str(cdir / "audio.flac"), sine_pcm(), SR, subtype="PCM_16")
        (d / "songs" / cid / "result.json").write_text(json.dumps({
            "status": "complete", "identity": f"{i:064d}",
            "weights": {"mot": {"files": {"model.safetensors": {"sha256": REFERENCE["mot_sha256"]}}},
                        "vae": {"files": {"model.safetensors": {"sha256": REFERENCE["vae_sha256"]}}}},
            "artifacts": {"audio.flac": {"sha256": sha(cdir / "audio.flac")}}}))
        (d / "songs" / cid / "config.json").write_text(json.dumps(
            {"runtime_sha256": REFERENCE["yue2_runtime_sha256"]}))
    if gpu_ok:
        (d / "lifecycle").mkdir(exist_ok=True)
        (d / "lifecycle" / "s1").mkdir(exist_ok=True)
        (d / "lifecycle" / "s1" / "rws_gpu_identity").mkdir(parents=True, exist_ok=True)
        (d / "lifecycle" / "s1" / "lifecycle-receipt.json").write_text(json.dumps({
            "receipt_type": "gpu_lifecycle", "cleanup_state": "CLEAN",
            "spawn": {"pid": 7, "starttime": "9", "session": 7},
            "server_exit": 0, "cmd_rc": 0,
            "steps": [{"step": "gpu_identity", "status": "GPU_EXECUTION_VERIFIED",
                       "bdf": "0000:03:00.0", "gpu_execution": "VERIFIED"}]}))
        (d / "lifecycle" / "s1" / "rws_gpu_identity" / "gpu.json").write_text(json.dumps(
            {"status": "GPU_EXECUTION_VERIFIED", "device": {"bdf": "0000:03:00.0",
                                                            "unique_id": "e9d0e20bb686e6c6"}}))
    return d


def test_V04_journal_count_alone_cannot_award_full_verdict(tmp_path):
    camp = make_campaign(tmp_path, n=384, song_dirs=8, gpu_ok=True)
    out, rc = run_verify(camp)
    assert out["verdict"] not in ("VERIFIED_REFERENCE_RUN", "VERIFIED_FULL_BENCHMARK",
                                  "VERIFIED_FULL_GENERATION"), out


def test_V05_audio_corruption_beyond_sampled_prefix_detected(tmp_path):
    camp = make_campaign(tmp_path, n=10, song_dirs=10, corrupt_from=8)
    out, rc = run_verify(camp)
    assert out["verdict"] not in ("VERIFIED_FULL_GENERATION", "VERIFIED_REFERENCE_RUN",
                                  "VALID_PILOT_ONLY"), out


def test_V05b_quick_mode_never_awards_full_verdict(tmp_path):
    camp = make_campaign(tmp_path, n=10, song_dirs=10)
    out, rc = run_verify(camp, "--quick")
    assert out["verdict"] == "SAMPLED_INTEGRITY_CHECK", out
    assert out.get("sampled_only") is True


def test_V06_campaign_gpu_identity_missing_caps_verdict(tmp_path):
    camp = make_campaign(tmp_path, n=10, song_dirs=10, gpu_ok=False)
    out, rc = run_verify(camp)
    assert out["verdict"] not in ("VERIFIED_REFERENCE_RUN", "VERIFIED_BENCHMARK_PILOT",
                                  "VERIFIED_FULL_GENERATION"), out
    assert out["verification_scope"]["gpu_execution"] != "VERIFIED"


def test_V07b_campaign_runtime_sha_none_rejected(tmp_path):
    camp = make_campaign(tmp_path, n=10, song_dirs=10, runtime_sha=None)
    out, rc = run_verify(camp)
    assert out["verdict"] not in ("VERIFIED_REFERENCE_RUN", "VERIFIED_FULL_GENERATION"), out
    assert out["verification_scope"]["runtime_provenance"] != "VERIFIED"


def test_V08_full_generation_without_evaluation_is_scope_limited(tmp_path):
    camp = make_campaign(tmp_path, n=384, song_dirs=384)
    out, rc = run_verify(camp)
    assert out["verdict"] == "VERIFIED_FULL_GENERATION", out
    assert out["verification_scope"]["evaluation_coverage"] != "VERIFIED"
    assert out["verdict"] != "VERIFIED_REFERENCE_RUN"


def test_V09_arbitrary_complete_count_is_not_a_pilot(tmp_path):
    camp = make_campaign(tmp_path, n=3, song_dirs=3)
    out, rc = run_verify(camp)
    assert out["verdict"] not in ("VALID_PILOT_ONLY", "VERIFIED_BENCHMARK_PILOT"), out


def test_V09b_official_pilot_shape_is_recognized(tmp_path):
    ids = [f"wsb_{p:03d}_r{j}_s{831000+p*2+j}" for p in (0, 1, 2, 79, 81) for j in (0, 1)]
    camp = make_campaign(tmp_path, n=10, song_dirs=10, ids=ids)
    out, rc = run_verify(camp)
    assert out["verdict"] in ("VALID_PILOT_ONLY", "VERIFIED_BENCHMARK_PILOT"), out


# ---------------------------------------------------------------- V10
def test_V10_compare_computes_real_metric_deltas(tmp_path):
    run = make_bundle(tmp_path / "song")
    (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run)))
    (run / "scoring").mkdir()
    (run / "scoring" / "summary.json").write_text(json.dumps({
        "five_metric": {"songbench": 6.5, "per": 9.0, "mulan": 0.49,
                        "allmusiccaps": 0.40, "q3o": 4.5},
        "coverage": {"songbench": 5, "per": 5, "mulan": 5, "allmusiccaps": 5, "q3o": 5}}))
    out, rc = run_verify(run, "--compare-reference")
    cmp = out.get("reference_comparison")
    assert isinstance(cmp, dict), out
    rows = cmp.get("metrics")
    assert isinstance(rows, dict) and set(rows) >= {"songbench", "per", "q3o"}, out
    assert rows["songbench"]["reference_value"] is not None
    assert rows["songbench"]["observed_value"] == 6.5
    assert abs(rows["songbench"]["absolute_delta"] - (6.5 - rows["songbench"]["reference_value"])) < 1e-9


def test_V10b_compare_without_user_scoreboard_is_explicitly_not_performed(tmp_path):
    run = make_bundle(tmp_path / "song")
    (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run)))
    out, rc = run_verify(run, "--compare-reference")
    cmp = out.get("reference_comparison", {})
    assert cmp.get("status") == "NOT_PERFORMED", out
    assert cmp.get("reason")


def test_verdict_always_carries_verification_scope(tmp_path):
    run = make_bundle(tmp_path / "song")
    out, rc = run_verify(run)
    assert "verification_scope" in out and isinstance(out["verification_scope"], dict)


# ------------------------------------------------- extended negative controls
def test_NC_gpu_receipt_from_another_run(tmp_path):
    run = make_bundle(tmp_path / "song")
    other = tmp_path / "other-run"
    other.mkdir()
    (other / "request.json").write_text("{}")
    (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run, request_path=str(other / "request.json"))))
    out, rc = run_verify(run)
    assert out["verdict"] == "FAILED", out


def test_NC_gpu_receipt_wrong_bdf(tmp_path):
    run = make_bundle(tmp_path / "song")
    (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run, bdf="0000:23:00.0")))
    out, rc = run_verify(run, "--expect-bdf", "0000:03:00.0")
    assert out["verdict"] == "FAILED", out


def test_NC_wrong_model_sha(tmp_path):
    run = make_bundle(tmp_path / "song", weights_ok=False)
    (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run)))
    out, rc = run_verify(run)
    assert out["verdict"] == "FAILED", out
    assert rc == 1


def test_NC_wrong_runtime_sha(tmp_path):
    run = make_bundle(tmp_path / "song", runtime_sha="e" * 64)
    (run / "lifecycle-receipt.json").write_text(json.dumps(gpu_receipt(run)))
    out, rc = run_verify(run)
    assert out["verdict"] == "FAILED", out


def test_NC_campaign_duplicate_ids(tmp_path):
    ids = [f"wsb_{p:03d}_r{j}_s{831000+p*2+j}" for p in (0, 1, 2, 79, 81) for j in (0, 1)]
    ids = ids + [ids[0]]           # 11 rows, one duplicate
    camp = make_campaign(tmp_path, n=11, song_dirs=10, ids=ids)
    out, rc = run_verify(camp)
    assert out["verdict"] == "FAILED", out
    assert any("duplicate" in p for p in out["problems"])


def test_NC_fake_384_ids_not_official_shape(tmp_path):
    ids = [f"fake_{i:03d}_r{i % 2}_s{i}" for i in range(384)]
    camp = make_campaign(tmp_path, n=384, song_dirs=8, ids=ids)
    out, rc = run_verify(camp)
    assert out["verdict"] != "VERIFIED_FULL_GENERATION", out


def test_NC_truncated_run_presented_as_full(tmp_path):
    ids = [f"wsb_{p:03d}_r{j}_s{831000+p*2+j}" for p in range(192) for j in (0, 1)]
    camp = make_campaign(tmp_path, n=383, song_dirs=383, ids=ids)
    out, rc = run_verify(camp)
    assert out["verdict"] in ("INCOMPLETE", "FAILED"), out


def test_NC_malformed_journal_line(tmp_path):
    ids = [f"wsb_{p:03d}_r{j}_s{831000+p*2+j}" for p in (0, 1, 2, 79, 81) for j in (0, 1)]
    camp = make_campaign(tmp_path, n=10, song_dirs=10, ids=ids)
    j = camp / "journal.jsonl"
    j.write_text(j.read_text() + '{"event": "result", "id": "wsb_000_r0_s8310 broken\n')
    out, rc = run_verify(camp)
    assert out["verdict"] == "FAILED", out
    assert any("malformed" in p for p in out["problems"])


def test_NC_missing_song_dir_for_journal_row(tmp_path):
    ids = [f"wsb_{p:03d}_r{j}_s{831000+p*2+j}" for p in (0, 1, 2, 79, 81) for j in (0, 1)]
    camp = make_campaign(tmp_path, n=10, song_dirs=9, ids=ids)   # one row has no bundle
    out, rc = run_verify(camp)
    assert out["verdict"] == "FAILED", out
