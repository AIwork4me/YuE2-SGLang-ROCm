"""Regression tests for verify_wsb_artifacts.py (hardened full/subset modes).

Run: source environments/yue2/bin/activate && python -m pytest tests/test_verify_wsb_artifacts.py -v

Builds small synthetic run directories with REAL artifact bundles (valid
hashes, flac audio, official-style request/config/result files) and asserts:

1. A 10-candidate subset can NEVER pass full mode (missing 374 reported).
2. The same subset passes subset mode with --expect 10.
3. --expect that disagrees with the selection is rejected, never adjusted.
4. A duplicate candidate directory fails.
5. An unexpected (stale) candidate directory fails.
6. A wrong seed inside request.json is reported.
7. A tampered artifact (hash mismatch) fails the official verify_result.
8. expected_from_manifest builds exactly 384 entries over 192 prompts.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

WS = Path(__file__).resolve().parents[1]
SCRIPT = WS / "scripts" / "verify_wsb_artifacts.py"
sys.path.insert(0, str(SCRIPT.parent))
import verify_wsb_artifacts as V  # noqa: E402

ENV = {**__import__("os").environ, "WS": str(WS)}


def _write_bundle(cand: Path, *, i: int, j: int, seed: int, style: str, lyrics: str,
                  ident: str, tamper: str | None = None, seed_override: int | None = None) -> None:
    cand.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    frames = 32
    audio = rng.normal(0, 0.1, (frames * 16, 2)).clip(-1, 1)
    sf.write(cand / "audio.flac", audio, 48000, subtype="PCM_24")
    np.save(cand / "semantic.npy", rng.integers(0, 32768, frames, dtype=np.int32))
    np.save(cand / "prefix.npy", rng.integers(0, 1000, 8, dtype=np.int32))
    np.save(cand / "latent.npy", rng.normal(size=(frames, 64)).astype(np.float32))
    request = {"style": style, "lyrics": lyrics, "cot": "full", "seed": seed_override or seed,
               "abc": None, "cfg_scale": 1.0, "id": ident}
    (cand / "request.json").write_text(json.dumps(request, indent=2) + "\n")
    (cand / "config.json").write_text(json.dumps({"generation": "x", "backend": "torch"}) + "\n")
    weights = {"mot": {"files": {"model.safetensors": {"sha256": "a" * 64, "bytes": 1}}, "config_sha256": "b" * 64},
               "vae": {"files": {"model.safetensors": {"sha256": "c" * 64, "bytes": 1}}, "config_sha256": "d" * 64}}
    blob = json.dumps({"request": request, "config": {"generation": "x", "backend": "torch"},
                       "weights": weights}, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    identity = hashlib.sha256(blob.encode()).hexdigest()

    def sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    artifacts = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size}
                 for p in sorted(cand.iterdir()) if p.name != "result.json"}
    result = {"status": "complete", "identity": identity, "truncated": False,
              "sample_rate": 48000, "audio_seconds": frames * 16 / 48000,
              "weights": weights, "timing": {}, "artifacts": artifacts}
    (cand / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    if tamper == "audio":
        (cand / "audio.flac").write_bytes(b"tampered")


@pytest.fixture()
def run10(tmp_path: Path):
    """A synthetic 5-prompt x 2 subset run with fully valid bundles."""
    manifest = [json.loads(l) for l in
                (WS / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl").read_text().splitlines() if l.strip()]
    by_index = {r["prompt_index"]: r for r in manifest}
    runs = tmp_path / "run"
    (runs / "songs").mkdir(parents=True)
    selected = []
    for i in (0, 1, 2, 76, 77):
        row = by_index[i]
        for j, seed in enumerate(row["candidate_ar_seeds"][:2]):
            ident = f"wsb_{i:03d}_r{j}_s{seed}"
            _write_bundle(runs / "songs" / ident, i=i, j=j, seed=seed,
                          style=row["style"], lyrics=row["lyrics"], ident=ident)
            selected.append({"prompt_index": i, "candidate_index": j, "seed": seed, "path": f"songs/{ident}"})
    (runs / "evaluation_inputs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in selected))
    return runs, selected


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, env=ENV, cwd=str(WS))


def test_expected_from_manifest_is_384_over_192_prompts():
    rows = V.load_manifest()
    expected = V.expected_from_manifest(rows)
    assert len(expected) == 384
    assert len({k[0] for k in expected}) == 192
    assert all(expected[(i, 0)]["seed"] == 831001 + i and expected[(i, 1)]["seed"] == 831019 + i
               for i in range(192))


def test_subset_cannot_pass_full_mode(run10):
    runs, _ = run10
    proc = _run(["--runs", str(runs)])  # default mode = full
    assert proc.returncode != 0
    report = json.loads((runs / "audit.json").read_text())
    assert report["verdict"] == "PARTIAL"
    assert report["expected_candidates"] == 384
    assert report["verified_complete"] == 10
    missing = [p for p in report["problems"] if "missing (no candidate directory)" in p]
    assert len(missing) == 374, "a 10-candidate subset must fail full mode with exactly 374 missing"


def test_subset_mode_passes_with_exact_expectation(run10):
    runs, _ = run10
    proc = _run(["--runs", str(runs), "--mode", "subset", "--expect", "10"])
    assert proc.returncode == 0, proc.stderr
    report = json.loads((runs / "audit.json").read_text())
    assert report["verdict"] == "FULL"
    assert report["verified_complete"] == 10
    assert report["identity_reverified"] == 10


def test_mismatched_expect_is_rejected_never_adjusted(run10):
    runs, _ = run10
    proc = _run(["--runs", str(runs), "--mode", "subset", "--expect", "5"])
    assert proc.returncode != 0
    assert "never adjusted silently" in (proc.stderr + proc.stdout)


def test_expect_rejected_in_full_mode(run10):
    runs, _ = run10
    proc = _run(["--runs", str(runs), "--expect", "384"])
    assert proc.returncode != 0
    assert "not valid in full mode" in (proc.stderr + proc.stdout)


def test_duplicate_directory_fails(run10):
    """Copying candidate r0 over r1's slot: self-consistent bundle, wrong seed."""
    runs, _ = run10
    src = runs / "songs" / "wsb_000_r0_s831001"
    shutil.copytree(src, runs / "songs" / "wsb_000_r1_s831019", dirs_exist_ok=True)
    proc = _run(["--runs", str(runs), "--mode", "subset", "--expect", "10"])
    assert proc.returncode != 0
    problems = json.loads((runs / "audit.json").read_text())["problems"]
    assert any("seed 831001 != official 831019" in p for p in problems), problems


def test_unexpected_directory_fails(run10):
    runs, _ = run10
    (runs / "songs" / "wsb_199_r0_s831200").mkdir()
    proc = _run(["--runs", str(runs), "--mode", "subset", "--expect", "10"])
    assert proc.returncode != 0
    assert any("unexpected candidate directory" in p
               for p in json.loads((runs / "audit.json").read_text())["problems"])


def test_wrong_seed_reported(run10):
    """Naive tamper: request.json edited -> its recorded hash breaks -> the
    official artifact-integrity check fires (first line of defense)."""
    runs, _ = run10
    cand = runs / "songs" / "wsb_000_r0_s831001"
    req = json.loads((cand / "request.json").read_text())
    req["seed"] = 831999  # wrong
    (cand / "request.json").write_text(json.dumps(req, indent=2) + "\n")
    proc = _run(["--runs", str(runs), "--mode", "subset", "--expect", "10"])
    assert proc.returncode != 0
    problems = json.loads((runs / "audit.json").read_text())["problems"]
    assert any("artifact integrity FAILED" in p for p in problems)


def test_forged_bundle_caught_by_identity_recheck(run10):
    """Consistent forgery: request seed changed AND result.json hashes and
    identity rewritten to stay self-consistent. The protocol seed check and
    the recomputed-identity comparison must both flag it."""
    runs, _ = run10
    cand = runs / "songs" / "wsb_000_r1_s831019"
    req = json.loads((cand / "request.json").read_text())
    req["seed"] = 831999  # wrong seed, forged below
    (cand / "request.json").write_text(json.dumps(req, indent=2) + "\n")
    result = json.loads((cand / "result.json").read_text())
    sha = hashlib.sha256((cand / "request.json").read_bytes()).hexdigest()
    result["artifacts"]["request.json"] = {"sha256": sha,
                                           "bytes": (cand / "request.json").stat().st_size}
    result["identity"] = "0" * 64  # attacker-consistent-but-unverifiable
    (cand / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    proc = _run(["--runs", str(runs), "--mode", "subset", "--expect", "10"])
    assert proc.returncode != 0
    problems = json.loads((runs / "audit.json").read_text())["problems"]
    assert any("seed 831999 != official 831019" in p for p in problems)
    assert any("identity" in p for p in problems), problems


def test_tampered_artifact_fails_official_check(run10):
    runs, _ = run10
    _write_bundle(runs / "songs" / "wsb_000_r1_s831019", i=0, j=1, seed=831019,
                  style="s", lyrics="l", ident="wsb_000_r1_s831019", tamper="audio")
    proc = _run(["--runs", str(runs), "--mode", "subset", "--expect", "10"])
    assert proc.returncode != 0
    assert any("artifact integrity FAILED" in p
               for p in json.loads((runs / "audit.json").read_text())["problems"])


def test_driver_failures_are_reported(run10):
    runs, _ = run10
    with (runs / "generation_manifest.jsonl").open("a") as f:
        f.write(json.dumps({"id": "wsb_001_r0_s831002", "status": "generation_failed",
                            "error": "x"}) + "\n")
    proc = _run(["--runs", str(runs), "--mode", "subset", "--expect", "10"])
    assert proc.returncode != 0
    assert any("driver status 'generation_failed'" in p
               for p in json.loads((runs / "audit.json").read_text())["problems"])
