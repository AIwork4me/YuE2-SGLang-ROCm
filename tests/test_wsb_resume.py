"""Resume / crash-safety behavior tests for run_wsb.py v2 (Phase 6).

Unit + light-integration (no GPU, no live server):
  - run identity is immutable (mixing runs refused)
  - evaluation_inputs.jsonl is write-once (protocol cannot silently change)
  - atomic_write leaves no temp files and replaces cleanly
  - a stale/partial candidate is QUARANTINED (never deleted), journaled, and a
    failing server produces generation_failed records + a valid summary
    (crash-safe restart evidence)
  - resume skips candidates whose result.json verifies (candidate_complete)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
RUN_WSB = SCRIPTS / "run_wsb.py"
sys.path.insert(0, str(SCRIPTS))

import run_wsb  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_artifact_storage():
    """Host-specific isolation fix (RC2 review): on a manifest-equipped host,
    an earlier test file (e.g. test_restoration_audit) can import the REAL
    frozen artifact_storage into sys.modules; run_wsb.candidate_complete's
    sys.path insertion then silently resolves to that cached module instead
    of this file's stub, breaking the stub-based resume tests. Purge the
    cache module around every test in this file (order-independent)."""
    saved = sys.modules.pop("artifact_storage", None)
    yield
    if saved is not None:
        sys.modules["artifact_storage"] = saved
    else:
        sys.modules.pop("artifact_storage", None)


def test_atomic_write(tmp_path):
    p = tmp_path / "a.json"
    run_wsb.atomic_write(p, '{"x": 1}\n')
    assert p.read_text() == '{"x": 1}\n'
    run_wsb.atomic_write(p, '{"x": 2}\n')
    assert p.read_text() == '{"x": 2}\n'
    assert not list(tmp_path.glob("*.tmp")), "temp files leaked"


def test_run_config_immutable(tmp_path):
    ident = {"run_id": "r1", "platform": "gfx1100", "config": run_wsb.OFFICIAL}
    assert run_wsb.check_or_write_run_config(tmp_path, ident) == 0
    assert run_wsb.check_or_write_run_config(tmp_path, ident) == 0  # idempotent
    bad = dict(ident, run_id="r2")
    assert run_wsb.check_or_write_run_config(tmp_path, bad) == 3   # refuse mixing


def test_evaluation_inputs_write_once(tmp_path):
    assert run_wsb.check_or_write_inputs(tmp_path, "a\nb\n") == 0
    assert run_wsb.check_or_write_inputs(tmp_path, "a\nb\n") == 0
    assert run_wsb.check_or_write_inputs(tmp_path, "a\nc\n") == 3


def test_candidate_complete_requires_official_verify(tmp_path, monkeypatch):
    # stub the official checker
    fake = tmp_path / "benchmark" / "wsb_metrics"
    fake.mkdir(parents=True)
    (fake / "artifact_storage.py").write_text(
        "def verify_result(c):\n    import json,pathlib\n"
        "    r=json.loads((pathlib.Path(c)/'result.json').read_text())\n"
        "    assert r['status']=='complete'\n    return r\n")
    monkeypatch.setattr(run_wsb, "WS", tmp_path)
    cand = tmp_path / "cand"
    cand.mkdir()
    (cand / "result.json").write_text('{"status": "aborted"}')
    assert run_wsb.candidate_complete(cand) is False
    (cand / "result.json").write_text('{"status": "complete"}')
    assert run_wsb.candidate_complete(cand) is True


def test_driver_quarantines_partial_and_journals_failure(tmp_path, monkeypatch):
    """End-to-end driver behavior against a dead server: quarantine, journal, summary."""
    ws = tmp_path / "ws"
    for sub in ("benchmark/WildSongBench/benchmark", "benchmark/wsb_metrics",
                "models/YuE2-3B", "models/YuE2-Vae-legacy"):
        (ws / sub).mkdir(parents=True)
    rows = [{"prompt_index": i, "candidate_ar_seeds": [831001 + i, 831019 + i] + [0] * 6,
             "style": "s", "lyrics": "l"} for i in range(192)]
    (ws / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    (ws / "benchmark/wsb_metrics/artifact_storage.py").write_text(
        "def verify_result(c):\n    raise FileNotFoundError('incomplete')\n")
    runs = ws / "runs/pilot"
    cand = runs / "songs/wsb_000_r0_s831001"
    cand.mkdir(parents=True)
    (cand / "partial.bin").write_bytes(b"\x00" * 16)
    (cand / "result.json").write_text('{"status": "complete"}')  # but stub always fails -> partial

    env = dict(os.environ, YUE2_WORKSPACE=str(ws), YUE2_PLATFORM="gfx1100-test",
               YUE2_GPU="test", YUE2_TORCH="test", YUE2_MIN_FREE_GB="0")
    r = subprocess.run(
        [sys.executable, str(RUN_WSB), "--runs", str(runs),
         "--indices", "0", "--server", "http://127.0.0.1:1",
         "--timeout", "2", "--max-retries", "0"],
        capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 1, r.stdout[-500:]

    # stale partial artifact preserved under quarantine, original gone
    q = list((runs / "quarantine").rglob("wsb_000_r0_s831001"))
    assert q, "partial artifact was deleted instead of quarnaantined"
    assert (q[0] / "partial.bin").read_bytes() == b"\x00" * 16
    assert not cand.exists()

    manifest = [json.loads(l) for l in
                (runs / "generation_manifest.jsonl").read_text().splitlines()]
    statuses = {m["status"] for m in manifest}
    assert "quarantined(partial)" in statuses
    assert "generation_failed" in statuses
    summary = json.loads((runs / "generation_summary.json").read_text())
    assert summary["expected"] == 2 and summary["failed"] == 2
    assert summary["complete"] == 0 and summary["pending"] == 0
    # run identity recorded and immutable
    cfg = json.loads((runs / "run_config.json").read_text())
    assert cfg["platform"] in ("gfx1100", "gfx1100-test"), cfg["platform"]
    assert cfg["config"]["ode_steps"] == 32
    assert cfg["config"]["semantic_max_tokens"] == 9000


def test_resume_skips_complete(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / "benchmark/WildSongBench/benchmark").mkdir(parents=True)
    (ws / "benchmark/wsb_metrics").mkdir(parents=True)
    rows = [{"prompt_index": i, "candidate_ar_seeds": [831001 + i, 831019 + i] + [0] * 6,
             "style": "s", "lyrics": "l"} for i in range(192)]
    (ws / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    (ws / "benchmark/wsb_metrics/artifact_storage.py").write_text(
        "def verify_result(c):\n    return {'status': 'complete'}\n")
    monkeypatch.setattr(run_wsb, "WS", ws)
    runs = ws / "runs/r"
    (runs / "songs/wsb_000_r0_s831001").mkdir(parents=True)
    (runs / "songs/wsb_000_r0_s831001/result.json").write_text('{"status": "complete"}')
    assert run_wsb.candidate_complete(runs / "songs/wsb_000_r0_s831001") is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


def test_resume_journals_exact_complete_status(tmp_path, monkeypatch):
    """RC2 R1-D1: a pre-verified candidate resumed by the driver must be
    journaled with status exactly 'complete' (+ resumed flag) — the chain's
    advancement gate counts exact-prefix matches, and the historical
    'complete(resumed)' spelling could stall recovery into a relaunch loop."""
    ws = tmp_path / "ws"
    (ws / "benchmark/WildSongBench/benchmark").mkdir(parents=True)
    (ws / "benchmark/wsb_metrics").mkdir(parents=True)
    rows = [{"prompt_index": i, "candidate_ar_seeds": [831001 + i, 831019 + i],
             "style": "s", "lyrics": "l"} for i in range(192)]
    (ws / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    (ws / "benchmark/wsb_metrics/artifact_storage.py").write_text(
        "import json, pathlib\n"
        "def verify_result(c):\n"
        "    p = pathlib.Path(c)\n"
        "    r = json.loads((p / 'result.json').read_text())\n"
        "    if r.get('status') != 'complete':\n"
        "        raise ValueError('not complete')\n"
        "    return r\n")
    runs = ws / "runs/r"
    cand = runs / "songs/wsb_000_r0_s831001"
    cand.mkdir(parents=True)
    (cand / "result.json").write_text('{"status": "complete"}')
    monkeypatch.setattr(run_wsb, "WS", ws)
    monkeypatch.setattr(run_wsb, "MANIFEST",
                        ws / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl")
    monkeypatch.setattr(run_wsb, "MODEL_DIR", ws / "models/YuE2-3B")
    monkeypatch.setattr(run_wsb, "VAE_DIR", ws / "models/YuE2-Vae-legacy")
    monkeypatch.setattr(run_wsb, "detect_platform",
                        lambda: {"platform": "t", "gpu": "t", "torch": "t"})
    monkeypatch.setattr(run_wsb, "patchset_hash", lambda: "0" * 64)

    monkeypatch.setattr(run_wsb, "MIN_FREE_GB", 0.0)  # tmpfs is small
    argv = ["--runs", str(runs), "--indices", "0", "--run-id", "t",
            "--server", "http://127.0.0.1:1", "--max-retries", "0",
            "--timeout", "2"]
    monkeypatch.setattr(sys, "argv", [str(RUN_WSB), *argv])
    rc = run_wsb.main()
    # candidate 0 resumed; candidate 1 fails fast against the dead server
    assert rc == 1
    manifest = [json.loads(l) for l in
                (runs / "generation_manifest.jsonl").read_text().splitlines()
                if l.strip()]
    by_id = {r["id"]: r for r in manifest}
    resumed = by_id["wsb_000_r0_s831001"]
    assert resumed["status"] == "complete"
    assert resumed.get("resumed") is True
    assert by_id["wsb_000_r1_s831019"]["status"] == "generation_failed"
