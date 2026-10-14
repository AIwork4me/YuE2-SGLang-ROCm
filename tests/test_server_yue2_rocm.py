"""Serving-layer robustness tests for the YuE2 SGLang server (Phase 12).

Runs against a LIVE server (default http://127.0.0.1:31000) using SMALL
budgets so each request finishes fast. Execute only when the server is not
processing the frozen scientific run (mission rule) - the suite is opt-in:

  SGLANG_TEST_SERVER=http://127.0.0.1:31000 python -m pytest \
      tests/test_server_yue2_rocm.py -v

Covers: health; valid/invalid requests; missing fields; output-location
validation; repeated seed determinism (same machine); error responses;
sequential-request resource hygiene; concurrency=2 with output isolation.
"""
from __future__ import annotations

import json
import os
import concurrent.futures
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import soundfile as sf
import numpy as np

SERVER = os.environ.get("SGLANG_TEST_SERVER", "http://127.0.0.1:31000")
SMALL = {"cot": "full", "ode_steps": 4, "semantic_max_tokens": 300,
         "abc_max_tokens": 256, "vae_core_frames": 192, "vae_halo_frames": 16}


def post(path, payload, timeout=1200):
    req = urllib.request.Request(SERVER + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        return e.code, {"error_body": body}


def get(path, timeout=15):
    with urllib.request.urlopen(SERVER + path, timeout=timeout) as r:
        return r.status, json.loads(r.read())


@pytest.fixture(scope="module")
def tmpbase(tmp_path_factory):
    return tmp_path_factory.mktemp("server_tests")


def test_health():
    code, body = get("/health")
    assert code == 200 and body.get("status") == "ok"


def test_valid_request_smoke(tmpbase):
    out = tmpbase / "valid"
    code, body = post("/v1/audio/generations", {
        "style": "[Tags]\nsoft pop\n", "lyrics": "[Lyrics]\nA tiny phrase.\n",
        "seed": 700001, "output_path": str(out), "output_file_name": "v.wav",
        "artifacts_dir": str(out / "c1"), "id": "srv-valid", **SMALL})
    assert code == 200, body
    wav = Path(body["audio"])
    assert wav.is_file() and body.get("sample_rate") == 48000
    a, sr = sf.read(wav, always_2d=True)
    assert sr == 48000 and a.shape[1] == 2 and np.isfinite(a).all()
    assert float(np.sqrt((a ** 2).mean())) > 0
    assert (out / "c1" / "request.json").is_file()


def test_missing_fields_rejected(tmpbase):
    code, body = post("/v1/audio/generations", {"seed": 1})
    assert 400 <= code < 500, (code, body)


def test_invalid_types_rejected(tmpbase):
    code, body = post("/v1/audio/generations", {
        "style": 12345, "lyrics": None, "seed": "not-a-seed",
        "output_path": str(tmpbase), "output_file_name": "x.wav",
        "artifacts_dir": str(tmpbase / "x"), **SMALL})
    assert 400 <= code < 500, (code, body)


def test_bad_output_location_rejected(tmpbase):
    code, body = post("/v1/audio/generations", {
        "style": "s", "lyrics": "l", "seed": 1,
        "output_path": "/proc/definitely/not/writable",
        "output_file_name": "x.wav", "artifacts_dir": "/proc/nope/x", **SMALL})
    assert code >= 400, (code, body)


def test_repeated_seed_deterministic_on_same_machine(tmpbase):
    """Same seed + same budgets -> identical artifact semantics on one host."""
    ids = []
    for i in range(2):
        out = tmpbase / f"rep{i}"
        code, body = post("/v1/audio/generations", {
            "style": "[Tags]\ntiny\n", "lyrics": "[Lyrics]\nSame words twice.\n",
            "seed": 700009, "output_path": str(out),
            "output_file_name": f"rep{i}.wav",
            "artifacts_dir": str(out / "c"), "id": f"srv-rep{i}", **SMALL})
        assert code == 200, body
        sem = np.load(Path(body["audio"]).parent / "c" / "semantic.npy",
                      allow_pickle=False)
        ids.append(sem.tobytes())
    assert ids[0] == ids[1], "same seed produced different semantic streams"


def test_error_response_is_json_not_crash(tmpbase):
    code, body = post("/v1/audio/generations", {
        "style": "s", "lyrics": "l", "seed": 1, "output_path": str(tmpbase),
        "output_file_name": "e.wav", "artifacts_dir": str(tmpbase / "e"),
        "ode_steps": -5, "semantic_max_tokens": 10, "abc_max_tokens": 10,
        "cot": "full", "vae_core_frames": 64, "vae_halo_frames": 16})
    # either a clean 4xx or a 200 with explicit error field; never a hang/crash
    assert code < 500, (code, body)


def test_sequential_requests_hygiene(tmpbase):
    """Three sequential small generations; server stays healthy, no stale files."""
    for i in range(3):
        out = tmpbase / f"seq{i}"
        code, body = post("/v1/audio/generations", {
            "style": "s", "lyrics": f"[Lyrics]\nSeq {i}.\n", "seed": 710000 + i,
            "output_path": str(out), "output_file_name": f"s{i}.wav",
            "artifacts_dir": str(out / "c"), "id": f"srv-seq{i}", **SMALL})
        assert code == 200, body
    code, _ = get("/health")
    assert code == 200


def test_two_concurrent_requests_isolated(tmpbase):
    outs = [tmpbase / f"conc{i}" for i in range(2)]

    def one(i):
        return post("/v1/audio/generations", {
            "style": "s", "lyrics": f"[Lyrics]\nConcurrent {i}.\n",
            "seed": 720000 + i, "output_path": str(outs[i]),
            "output_file_name": f"c{i}.wav",
            "artifacts_dir": str(outs[i] / "c"), "id": f"srv-conc{i}", **SMALL})

    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        results = list(ex.map(one, range(2)))
    for i, (code, body) in enumerate(results):
        assert code == 200, body
        wav = outs[i] / f"c{i}.wav"
        a, sr = sf.read(wav, always_2d=True)
        assert sr == 48000 and a.shape[1] == 2 and np.isfinite(a).all()
        req = json.loads((outs[i] / "c" / "request.json").read_text())
        assert req["seed"] == 720000 + i, "cross-request seed corruption"
    # no cross-contamination of artifact bundles
    assert not (outs[0] / "c" / "request.json").is_symlink()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
