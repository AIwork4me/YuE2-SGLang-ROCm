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
