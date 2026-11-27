"""RC5.1 resume-gate decision unit tests (torch-free, CPU CI).

rc5_generate.py:setup() compares the frozen run_config.json identity with the
identity measured at relaunch. The decision is a pure function so it can be
tested without torch/sglang/GPU:

  * frozen fields (runtime, environment, dataset, models, official config,
    selection, GPU card identity, official verifier) must match EXACTLY;
  * per-session fields (receipt/log paths, created_at, dirty flag) may differ;
  * a repo-head move alone (docs / CI commits) is accepted and disclosed;
  * a changed driver script additionally requires --allow-driver-update;
  * nothing ever rewrites run_config.json to hide a mismatch.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _driver():
    spec = importlib.util.spec_from_file_location("rc5_generate", REPO / "scripts" / "rc5_generate.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _frozen_identity():
    return {
        "run_id": "r", "arm": "ARM_B_LATEST_UPSTREAM_RC5",
        "driver_repo_head": "a" * 40, "driver_repo_dirty": True,
        "driver_sha256": "b" * 64,
        "runtime": {"torch_version": "2.12.0+rocm7.14.1",
                    "yue2_runtime_sha256": "c" * 64},
        "environment_freeze_sha256": "d" * 64,
        "dataset_revision": "e" * 40, "dataset_manifest_sha256": "f" * 64,
        "model_revision": "m-a-p/YuE2-3B@x", "model_sha256": "1" * 64,
        "vae_revision": "m-a-p/YuE2-Vae-legacy@y", "vae_sha256": "2" * 64,
        "config": {"cot": "full", "ode_steps": 32},
        "candidates": 2, "indices": None,
        "gpu": {"name": "AMD Radeon Pro W7900D", "arch": ["gfx1100"],
                "pci_bdf": "0000:03:00.0", "uuid": "u", "drm_card": "card1",
                "identity_status": "GPU_EXECUTION_VERIFIED",
                "identity_receipt": "/old/session/gpu.json"},
        "official_verifier_sha256": "3" * 64,
        "created_at_utc": "2026-11-24T06:55:53Z",
        "server_identity_is_per_launch": True,
        "server_log": "/old/session/server.log",
    }


def test_same_session_identity_is_accepted():
    m = _driver()
    prev = _frozen_identity()
    d = m.resume_decision(prev, dict(prev), allow_driver_update=False)
    assert d["accept"] and d["reason"] == "ok"
    assert not d["repo_head_moved"] and not d["driver_changed"]


def test_per_session_paths_and_metadata_may_drift():
    m = _driver()
    prev = _frozen_identity()
    new = dict(prev, created_at_utc="2026-11-25T00:00:00Z", driver_repo_dirty=False,
               server_log="/new/session/server.log",
               gpu=dict(prev["gpu"], identity_receipt="/new/session/gpu.json"))
    d = m.resume_decision(prev, new, allow_driver_update=False)
    assert d["accept"], d["drift"]


def test_repo_head_move_with_identical_driver_is_accepted_and_disclosed():
    m = _driver()
    prev = _frozen_identity()
    new = dict(prev, driver_repo_head="f" * 40)      # docs/CI commit, same script
    d = m.resume_decision(prev, new, allow_driver_update=False)
    assert d["accept"] and d["repo_head_moved"] and not d["driver_changed"]


def test_driver_script_change_requires_allow_driver_update():
    m = _driver()
    prev = _frozen_identity()
    new = dict(prev, driver_repo_head="f" * 40, driver_sha256="0" * 64)
    d = m.resume_decision(prev, new, allow_driver_update=False)
    assert not d["accept"]
    assert d["reason"] == "driver_script_changed_without_allow_driver_update"
    assert not d["drift"]                             # everything else matches
    d2 = m.resume_decision(prev, new, allow_driver_update=True)
    assert d2["accept"] and d2["driver_changed"] and d2["repo_head_moved"]


def test_frozen_runtime_drift_is_refused_even_with_allow_driver_update():
    m = _driver()
    prev = _frozen_identity()
    new = dict(prev, driver_sha256="0" * 64,
               runtime=dict(prev["runtime"], yue2_runtime_sha256="9" * 64))
    d = m.resume_decision(prev, new, allow_driver_update=True)
    assert not d["accept"] and d["reason"] == "frozen_generation_identity_drift"
    assert "runtime" in d["drift"]


def test_gpu_card_swap_is_refused():
    m = _driver()
    prev = _frozen_identity()
    new = dict(prev, gpu=dict(prev["gpu"], pci_bdf="0000:ff:00.0", uuid="other"))
    d = m.resume_decision(prev, new, allow_driver_update=True)
    assert not d["accept"]
    assert "gpu.pci_bdf" in d["drift"] and "gpu.uuid" in d["drift"]


def test_official_config_drift_is_refused():
    m = _driver()
    prev = _frozen_identity()
    new = dict(prev, config={"cot": "full", "ode_steps": 16})   # lowered budget
    d = m.resume_decision(prev, new, allow_driver_update=False)
    assert not d["accept"] and "config" in d["drift"]
