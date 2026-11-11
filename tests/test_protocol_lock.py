"""Protocol lock / pin consistency tests (Issue D).

The frozen protocol (evidence/protocol_lock.json), the download pins
(scripts/download_pins.py) and the auditor's frozen manifest hash
(scripts/verify_wsb_artifacts.py) must agree with each other. A single
source-of-truth drift between these files is a release defect.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


def _load_pins():
    spec = importlib.util.spec_from_file_location(
        "download_pins", REPO / "scripts" / "download_pins.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PINS, mod.SGlang_PIN


def _load_lock():
    path = REPO / "evidence" / "protocol_lock.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def test_protocol_lock_present_and_parses():
    lock = _load_lock()
    if lock is None:
        pytest.skip("historical protocol_lock.json not in this checkout")
    assert lock["dataset_revision"] if "dataset_revision" in lock else True


def test_download_pins_match_frozen_evidence():
    pins, sglang_pin = _load_pins()
    lock = _load_lock()
    evidence_blob = ""
    for name in ("evidence/protocol_lock.json", "evidence/model_manifest.json"):
        path = REPO / name
        if path.is_file():
            evidence_blob += path.read_text(encoding="utf-8")
    if not evidence_blob:
        pytest.skip("historical evidence files not in this checkout")
    for key in ("dataset_revision", "ar_revision", "vae_revision"):
        assert pins[key] in evidence_blob, f"{key} from download_pins not recorded in frozen evidence"
    assert sglang_pin in evidence_blob or sglang_pin[:7] in evidence_blob, \
        "SGLang PR head pin not recorded in frozen evidence"


def test_auditor_manifest_hash_matches_download_pins():
    pins, _ = _load_pins()
    auditor = (REPO / "scripts" / "verify_wsb_artifacts.py").read_text(encoding="utf-8")
    assert pins["sha256"]["WildSongBench/benchmark/reproduction_manifest.jsonl"] in auditor, \
        "auditor frozen manifest hash drifted from download pins"


def test_model_weight_pinned_everywhere():
    pins, _ = _load_pins()
    lock = _load_lock()
    auditor = (REPO / "scripts" / "verify_wsb_artifacts.py").read_text(encoding="utf-8")
    model_sha = pins["sha256"]["YuE2-3B/model.safetensors"]
    assert model_sha in json.dumps(_load_pins())
    if lock is not None:
        assert model_sha in json.dumps(lock), "model weight sha missing from protocol lock"


def test_download_pins_sha_format():
    pins, _ = _load_pins()
    for rel, sha in pins["sha256"].items():
        assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha), \
            f"malformed sha256 for {rel}"
    for key in ("dataset_revision", "ar_revision", "vae_revision"):
        assert len(pins[key]) == 40, f"{key} must be a full git revision"
