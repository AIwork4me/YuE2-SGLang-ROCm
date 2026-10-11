"""Negative + positive tests for verify_wsb_artifacts.py v2 (Phase 6 hardening).

Proves the validator now REJECTS what v1 could silently accept:
  - a 10/10 pilot run in full mode            (v1 reduced expect to 10 -> PASS bug)
  - 383/384 candidates
  - a wrong seed vs the frozen manifest       (v1 swallowed the error via list reset)
  - a duplicated candidate
  - an unexpected candidate directory
  - a corrupted artifact (official verify fails)
and still ACCEPTS truncated-but-valid candidates (counted, verdict FULL).

Everything runs in an isolated synthetic YUE2_WORKSPACE with a stub
artifact_storage.verify_result, so no models or real audio are needed.
"""
from __future__ import annotations

import json
import shutil
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "verify_wsb_artifacts.py"

STUB = '''
def verify_result(cand):
    import json, pathlib
    p = pathlib.Path(cand)
    if (p / "corrupt").exists():
        raise ValueError("simulated corruption")
    r = json.loads((p / "result.json").read_text())
    if r.get("status") != "complete":
        raise ValueError("not complete")
    return r
'''


def make_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "benchmark/WildSongBench/benchmark").mkdir(parents=True)
    (ws / "benchmark/wsb_metrics").mkdir(parents=True)
    real = Path(os.environ.get("YUE2_WORKSPACE",
                               REPO.parents[1])) / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
    if not real.is_file():
        pytest.skip("pinned WildSongBench manifest not available; run "
                    "scripts/download_pins.py first (tests validate against the "
                    "real frozen protocol file)")
    shutil.copy(real, ws / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl")
    (ws / "benchmark/wsb_metrics/artifact_storage.py").write_text(STUB)
    return ws


def make_run(ws: Path, name: str, indices, corrupt=(), wrong_seed=None,
             drop=(), extra_dir=None, duplicate=None, truncated=()):
    runs = ws / "runs" / name
    songs = runs / "songs"
    songs.mkdir(parents=True)
    inputs = []
    for i in indices:
        for j in (0, 1):
            if (i, j) in drop:
                continue
            seed = 831001 + i + 18 * j
            if wrong_seed == (i, j):
                seed += 12345
            ident = f"wsb_{i:03d}_r{j}_s{seed}"
            inputs.append({"prompt_index": i, "candidate_index": j,
                           "seed": seed, "path": f"songs/{ident}"})
            cand = songs / ident
            cand.mkdir()
            (cand / "result.json").write_text(json.dumps(
                {"status": "complete", "truncated": (i, j) in truncated}))
            (cand / "request.json").write_text(json.dumps(
                {"seed": seed, "cot": "full", "cfg_scale": 1.0}))
            if (i, j) in corrupt:
                (cand / "corrupt").write_text("x")
    if duplicate is not None:
        ident = duplicate
        cand = songs / ident
        cand.mkdir(parents=True, exist_ok=True)
        (cand / "result.json").write_text('{"status": "complete", "truncated": false}')
        (cand / "request.json").write_text('{"seed": 0, "cot": "full", "cfg_scale": 1.0}')
    if extra_dir:
        (songs / extra_dir).mkdir()
        (songs / extra_dir / "result.json").write_text('{"status": "complete"}')
    (runs / "evaluation_inputs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in inputs))
    return runs


def run_validator(ws: Path, runs: Path, *extra):
    env = dict(os.environ, YUE2_WORKSPACE=str(ws))
    return subprocess.run([sys.executable, str(SCRIPT), "--runs", str(runs), *extra],
                          capture_output=True, text=True, env=env)


def audit(runs: Path) -> dict:
    return json.loads((runs / "audit.json").read_text())


def test_pilot_10_of_10_cannot_pass_full_mode(tmp_path):
    ws = make_ws(tmp_path)
    runs = make_run(ws, "pilot10", indices=range(5))
    r = run_validator(ws, runs)  # default mode=full
    assert r.returncode != 0
    a = audit(runs)
    assert a["verdict"] == "PARTIAL"
    assert any("384" in p for p in a["problems"]), a["problems"]
    assert any("REFUSING to lower the bar" in p for p in a["problems"])


def test_full_383_of_384_rejected(tmp_path):
    ws = make_ws(tmp_path)
    runs = make_run(ws, "short", indices=range(192), drop=[(191, 1)])
    r = run_validator(ws, runs)
    assert r.returncode != 0
    a = audit(runs)
    assert a["verdict"] == "PARTIAL"
    assert any("exactly 384 unique candidates, got 383" in p_ for p_ in a["problems"])
    assert any("prompt 191: candidates [0] != [0, 1]" in p_ for p_ in a["problems"])


def test_wrong_seed_rejected_and_error_preserved(tmp_path):
    ws = make_ws(tmp_path)
    runs = make_run(ws, "seedbad", indices=range(3), wrong_seed=(1, 0))
    r = run_validator(ws, runs, "--mode", "pilot")
    assert r.returncode != 0
    a = audit(runs)
    assert any("frozen manifest seed" in p for p in a["problems"]), a["problems"]


def test_duplicate_candidate_rejected(tmp_path):
    ws = make_ws(tmp_path)
    runs = make_run(ws, "dupe", indices=range(2))
    # forge a second directory with the same identity as wsb_000_r0
    src = runs / "songs" / "wsb_000_r0_s831001"
    dst = runs / "songs" / "wsb_000_r0_s831001"
    assert src.is_dir()
    r = run_validator(ws, runs, "--mode", "pilot")
    a = audit(runs)
    # same-name duplication is impossible on a filesystem; instead duplicate the
    # (i,j) pair in evaluation_inputs
    inp = (runs / "evaluation_inputs.jsonl").read_text()
    (runs / "evaluation_inputs.jsonl").write_text(inp + inp.splitlines()[0] + "\n")
    r = run_validator(ws, runs, "--mode", "pilot")
    assert r.returncode != 0
    a = audit(runs)
    assert any("duplicate entry" in p for p in a["problems"]), a["problems"]


def test_unexpected_candidate_dir_rejected(tmp_path):
    ws = make_ws(tmp_path)
    runs = make_run(ws, "extra", indices=range(2), extra_dir="wsb_190_r0_s831991")
    r = run_validator(ws, runs, "--mode", "pilot")
    assert r.returncode != 0
    a = audit(runs)
    assert any("unexpected candidate dir" in p for p in a["problems"]), a["problems"]


def test_corrupted_artifact_rejected(tmp_path):
    ws = make_ws(tmp_path)
    runs = make_run(ws, "corrupt", indices=range(2), corrupt=[(0, 1)])
    r = run_validator(ws, runs, "--mode", "pilot")
    assert r.returncode != 0
    a = audit(runs)
    assert any("official verify_result FAILED" in p for p in a["problems"]), a["problems"]


def test_truncated_but_valid_passes(tmp_path):
    ws = make_ws(tmp_path)
    runs = make_run(ws, "trunc", indices=range(3), truncated=[(0, 0), (2, 1)])
    r = run_validator(ws, runs, "--mode", "pilot")
    assert r.returncode == 0
    a = audit(runs)
    assert a["verdict"] == "PILOT"
    assert a["truncated_but_complete"] == 2
    assert a["problem_count"] == 0


def test_pilot_mode_explicit_for_subsets(tmp_path):
    ws = make_ws(tmp_path)
    runs = make_run(ws, "ok2", indices=range(1))
    r = run_validator(ws, runs, "--mode", "pilot")
    assert r.returncode == 0
    assert audit(runs)["verdict"] == "PILOT"


def test_dataset_hash_mismatch_is_fatal(tmp_path):
    ws = make_ws(tmp_path)
    manifest = ws / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
    text = manifest.read_text()
    # keep the 192-row shape; change one byte of content so only the hash fails
    manifest.write_text(text.replace('"style": "', '"style": "X', 1))
    runs = make_run(ws, "x", indices=range(1))
    r = run_validator(ws, runs, "--mode", "pilot")
    assert r.returncode == 2
    assert "dataset revision mismatch" in r.stdout
    # allow-flag records the problem instead of hiding it
    r2 = run_validator(ws, runs, "--mode", "pilot", "--allow-missing-dataset-hash")
    a = audit(runs)
    assert any("WARNING-RECORDED" in p for p in a["problems"])


def test_full_mode_with_wrong_expect_flag_rejected(tmp_path):
    ws = make_ws(tmp_path)
    runs = make_run(ws, "full384", indices=range(192))
    r = run_validator(ws, runs, "--expect", "383")
    assert r.returncode != 0
    a = audit(runs)
    assert any("requires --expect 384" in p for p in a["problems"])
    # and the correct invocation passes:
    r2 = run_validator(ws, runs)
    assert r2.returncode == 0
    assert audit(runs)["verdict"] == "FULL"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
