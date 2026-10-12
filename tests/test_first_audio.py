"""Phase 4: validation of the first gfx1151 generations (HTTP path).

Run after scripts/phase4 requests have been executed:
    source environments/yue2/bin/activate && python -m pytest tests/test_first_audio.py -v

Validates the actual server-produced files (no fixtures):
- runs/phase4/smoke1.wav  (small budget, cot=full)
- runs/phase4/full1.wav   (official budgets: ode 32 / 9000 / 4096 / 1024 / 16)
- runs/phase4/full1_repeat.wav (same seed as full1)
- runs/phase4/alias1.wav  (/v1/audio/music/generations)
- runs/phase4/full1_artifacts/ (WSB-style artifact bundle)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

RUNS = Path(os.environ.get("YUE2_WORKSPACE", "/home/amd/Desktop/YuE2")) / "runs/phase4"


def _meta(path: Path):
    audio, sr = sf.read(path)
    assert audio.ndim == 2, f"{path.name}: expected stereo"
    return {
        "sr": sr, "channels": audio.shape[1], "frames": len(audio),
        "duration_s": len(audio) / sr,
        "rms": float(np.sqrt((audio.astype(np.float64) ** 2).mean())),
        "peak": float(np.abs(audio).max()),
        "clip": float((np.abs(audio) > 0.999).mean()),
        "finite": bool(np.isfinite(audio).all()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_smoke_audio():
    m = _meta(RUNS / "smoke1.wav")
    assert m["sr"] == 48000 and m["channels"] == 2
    assert m["duration_s"] > 5 and m["rms"] > 1e-3
    assert m["finite"] and m["clip"] == 0.0


def test_full_audio():
    m = _meta(RUNS / "full1.wav")
    assert m["sr"] == 48000 and m["channels"] == 2
    # a full-song generation with 1720 semantic tokens @ 25 fps ~ 68.8 s
    assert 30 <= m["duration_s"] <= 400
    assert m["rms"] > 5e-3 and m["peak"] > 0.1
    assert m["finite"] and m["clip"] == 0.0


def test_same_seed_byte_identical():
    """Same request, same seed: byte-identical output on this stack (recorded;
    not a general determinism claim — see report)."""
    a = _meta(RUNS / "full1.wav")
    b = _meta(RUNS / "full1_repeat.wav")
    assert a["sha256"] == b["sha256"]
    assert a["duration_s"] == b["duration_s"]


def test_alias_route_audio():
    m = _meta(RUNS / "alias1.wav")
    assert m["sr"] == 48000 and m["channels"] == 2 and m["duration_s"] > 1
    assert m["finite"] and m["rms"] > 1e-4


def test_artifact_bundle():
    d = RUNS / "full1_artifacts"
    for name in ("latent.npy", "semantic.npy", "prefix.npy", "abc_tokens.npy",
                 "plan.json", "plan_manifest.json", "request.json"):
        assert (d / name).is_file(), name
    plan = json.loads((d / "plan.json").read_text())
    assert plan["request"]["cot"] == "full"
    assert plan["request"]["seed"] == 831001
    assert plan["truncated"] is False
    lat = np.load(d / "latent.npy")
    sem = np.load(d / "semantic.npy")
    assert lat.ndim == 2 and lat.shape[1] == 64 and np.isfinite(lat).all()
    assert sem.ndim == 1 and sem.dtype == np.int32 and len(sem) > 0
    # 25 codec frames per second <-> audio duration
    assert abs(len(sem) / 25.0 - _meta(RUNS / "full1.wav")["duration_s"]) < 2.0


def test_timing_and_backends_recorded():
    plan = json.loads((RUNS / "full1_artifacts" / "plan.json").read_text())
    t = plan["timing"]
    assert t["semantic"]["sampler"] == "reference"
    assert t["semantic"]["execution"] == "cuda_graph"
    assert t["semantic"]["attention"] == "flash"
    assert t["abc"]["output_tokens"] > 0 and t["semantic"]["output_tokens"] > 0
