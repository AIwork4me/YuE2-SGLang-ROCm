"""RC5.1 P0.3.2 — Q3O judge resume-identity controls (torch-free).

A Q3O receipt may only be reused when the ENTIRE judge identity matches:
code (judge + MoE blocks), evaluator bundle, model weights (content hash),
prompts, decoding config, precision, attention backend, torch, placement and
tie-break policy — and the audio bytes. The old flaw (any status=complete
receipt was reused) is pinned here as a negative control.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _judge_module():
    spec = importlib.util.spec_from_file_location("rc5_q3o_judge", REPO / "scripts" / "rc5_q3o_judge.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def judge():
    return _judge_module()


IDENT = "i" * 64
AUDIO = "a" * 64


def _receipt(status="complete", ident=IDENT, audio=AUDIO):
    return {"status": status, "identity_sha256": ident, "audio_sha256": audio,
            "scores": {"q3o": 4.83}}


def test_matching_receipt_is_reusable(judge):
    ok, why = judge.receipt_reusable(_receipt(), IDENT, AUDIO)
    assert ok and why == "reusable"


def test_not_applicable_is_reusable_when_identity_matches(judge):
    ok, why = judge.receipt_reusable(_receipt(status="not_applicable"), IDENT, AUDIO)
    assert ok and why == "reusable"


def test_failed_status_is_never_reused(judge):
    ok, why = judge.receipt_reusable(_receipt(status="failed"), IDENT, AUDIO)
    assert not ok and why == "status_failed"


def test_different_judge_code_is_never_reused(judge):
    ok, why = judge.receipt_reusable(_receipt(ident="f" * 64), IDENT, AUDIO)
    assert not ok and why == "judge_identity_mismatch"


def test_different_audio_is_never_reused(judge):
    ok, why = judge.receipt_reusable(_receipt(audio="0" * 64), IDENT, AUDIO)
    assert not ok and why == "audio_mismatch"


def test_legacy_receipt_without_identity_is_never_reused(judge):
    """The RC5 flaw: an old receipt with only status=complete must NOT be
    reusable even though its status looks good."""
    legacy = {"status": "complete", "scores": {"q3o": 4.83}}      # no identity fields
    ok, why = judge.receipt_reusable(legacy, IDENT, AUDIO)
    assert not ok and why == "judge_identity_mismatch"


def test_identity_drift_detects_every_frozen_key(judge):
    base = {"judge_source_sha256": "a", "moe_source_sha256": "b", "model_revision": "r",
            "torch_version": "2.10.0", "placement_config": {"gpu_layers": 34},
            "tie_break_policy": "lowest", "created_at_utc": "t1"}
    same = dict(base, created_at_utc="t2")                     # only wall-clock differs
    assert judge.identity_drift(base, same) == {}
    for key, new in (("judge_source_sha256", "z"), ("moe_source_sha256", "z"),
                     ("torch_version", "2.12.0"), ("tie_break_policy", "highest"),
                     ("placement_config", {"gpu_layers": 16})):
        assert key in judge.identity_drift(base, dict(base, **{key: new})), key
    assert "model_revision" in judge.identity_drift(base, dict(base, model_revision="other"))


def test_atomic_write_never_damages_existing_file(judge, tmp_path):
    dest = tmp_path / "receipts" / "x" / "q3o.json"
    judge.atomic_write_json(dest, {"a": 1})
    assert json.loads(dest.read_text()) == {"a": 1}
    judge.atomic_write_json(dest, {"a": 2})
    assert json.loads(dest.read_text()) == {"a": 2}
    assert not list(dest.parent.glob("*.tmp*"))                 # no torn temporaries left


def test_atomic_write_survives_serialisation_failure(judge, tmp_path, monkeypatch):
    dest = tmp_path / "q3o.json"
    judge.atomic_write_json(dest, {"ok": True})

    def boom(*a, **k):
        raise TypeError("not serialisable")

    monkeypatch.setattr(judge.json, "dumps", boom)
    with pytest.raises(TypeError):
        judge.atomic_write_json(dest, {"bad": object()})
    assert json.loads(dest.read_text()) == {"ok": True}          # original intact
