"""RC2 R1-D2 regression: the live-server suite must be OPT-IN.

test_server_yue2_rocm.py drives REAL generation requests. Its historical
default SERVER=http://127.0.0.1:31000 made a plain `pytest tests/` run on a
benchmark host send traffic to the frozen campaign server mid-run. The suite
must self-skip unless SGLANG_TEST_SERVER is explicitly provided (and must
also refuse while a GPU ownership lock is held).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _run_suite(env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("SGLANG_TEST_SERVER", "SGLANG_TEST_ALLOW_LOCKED",
                        "YUE2_GPU_LOCK", "YUE2_WORKSPACE")}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "pytest",
         str(REPO / "tests/test_server_yue2_rocm.py"), "-q", "-rs",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, env=env, timeout=120,
        cwd=str(REPO))


def test_skips_without_env():
    r = _run_suite({})
    # rc 5 ("no tests ran") is acceptable for a module-level skip under the
    # installed shard plugin; what matters: nothing executed, no failures
    assert r.returncode in (0, 5), r.stdout[-800:] + r.stderr[-800:]
    assert "skipped" in r.stdout
    assert "failed" not in r.stdout and "error" not in r.stdout.lower()


def test_source_contract_no_default_live_endpoint():
    """Source-level pin (mutation-killable without touching the network):
    the live-server suite must never default to a real endpoint."""
    src = (REPO / "tests/test_server_yue2_rocm.py").read_text()
    assert 'os.environ.get("SGLANG_TEST_SERVER", "")' in src
    assert 'os.environ.get("SGLANG_TEST_SERVER", "http' not in src
    assert "allow_module_level=True" in src


def test_skips_when_gpu_lock_is_held(tmp_path):
    lock = tmp_path / "gpu.lock"
    lock.write_text(json.dumps(
        {"who": "armB-campaign:armB_full_TEST", "pid": 1}))
    r = _run_suite({"SGLANG_TEST_SERVER": "http://127.0.0.1:1",
                    "YUE2_GPU_LOCK": str(lock)})
    assert r.returncode in (0, 5), r.stdout[-800:] + r.stderr[-800:]
    assert "skipped" in r.stdout
    assert "armB-campaign" in r.stdout or "disturb a live campaign" in r.stdout
