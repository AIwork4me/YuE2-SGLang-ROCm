#!/usr/bin/env python3
"""Negative controls for the RC6 A2 evaluator hardening (fail-closed resume +
scorer validation). Every control must FAIL CLOSED in the documented way;
a control that silently passes is a test failure.

Runs fully offline on synthetic fixtures (no audio, no models). Produces
02_ASR_NEGATIVE_CONTROLS.json via scripts/rc6_run_negative_controls.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rc6_asr_identity as asr_id  # noqa: E402


MANIFEST = [
    {"id": "c0", "prompt_index": 0, "candidate_index": 0, "lang": "en",
     "audio_sha256": "a" * 64},
    {"id": "c1", "prompt_index": 0, "candidate_index": 1, "lang": "en",
     "audio_sha256": "b" * 64},
    {"id": "c2", "prompt_index": 1, "candidate_index": 0, "lang": "zh",
     "audio_sha256": "c" * 64},
]


def make_identity(vllm="0.19.1", torch="2.10.0+rocm7.12.0", repeats=4, max_tokens=4096,
                  model_sha=None):
    return {
        "schema": asr_id.SCHEMA,
        "model": {"root": "/x", "snapshot": "snap", "files": {"f": (model_sha or "m" * 64)},
                  "files_sha256": model_sha or "m" * 64},
        "engine": {"engine": "vLLM native", "vllm": vllm, "torch": torch,
                   "hip": "7.12.6", "dtype": "bfloat16", "seed": 0},
        "audio_preprocessing": {"chunking": "split_audio_into_chunks"},
        "decoding": {"temperature": 0.0, "top_p": 1.0, "top_k": -1,
                     "max_tokens": max_tokens, "seed": 0, "repeats": repeats},
        "scoring": {"audio_manifest_sha256": "s" * 64},
        "driver": {"path": "/d", "sha256": "d" * 64},
    }


def receipt(cid="c0", audio="a" * 64, repeats=4, ident=None, status="complete"):
    r = {"id": cid, "prompt_index": 0, "candidate_index": 0, "lang": "en",
         "audio_sha256": audio, "chunks": 1,
         "repeats": [{"repeat": i, "text": "x"} for i in range(repeats)],
         "engine": {}, "run_identity": ident or make_identity(),
         "repeat_count": repeats, "status": status}
    r["transcript_receipt_sha256"] = asr_id.receipt_sha256(r)
    return r


def write(tmp_path, rows):
    p = tmp_path / "t.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_exact_identity_match_reuse(tmp_path):
    ident = make_identity()
    p = write(tmp_path, [receipt("c0", ident=ident), receipt("c1", audio="b" * 64, ident=ident)])
    a = asr_id.audit_receipts(p, MANIFEST, ident, expected_repeats=4)
    assert a["reusable"] == ["c0", "c1"] and a["resume_allowed"]


def test_audio_mismatch_rejected(tmp_path):
    ident = make_identity()
    p = write(tmp_path, [receipt("c0", audio="z" * 64, ident=ident)])
    a = asr_id.audit_receipts(p, MANIFEST, ident)
    assert a["decisions"]["c0"] == asr_id.R_AUDIO_MISMATCH and not a["resume_allowed"]


def test_model_mismatch_rejected(tmp_path):
    p = write(tmp_path, [receipt("c0", ident=make_identity(model_sha="q" * 64))])
    a = asr_id.audit_receipts(p, MANIFEST, make_identity())
    assert a["decisions"]["c0"] == asr_id.R_MODEL_MISMATCH


def test_engine_mismatch_rejected(tmp_path):
    p = write(tmp_path, [receipt("c0", ident=make_identity(vllm="0.14.0"))])
    a = asr_id.audit_receipts(p, MANIFEST, make_identity())
    assert a["decisions"]["c0"] == asr_id.R_ENGINE_MISMATCH


def test_config_mismatch_rejected(tmp_path):
    p = write(tmp_path, [receipt("c0", ident=make_identity(max_tokens=2048))])
    a = asr_id.audit_receipts(p, MANIFEST, make_identity())
    assert a["decisions"]["c0"] == asr_id.R_CONFIG_MISMATCH


def test_missing_repeats_incomplete(tmp_path):
    p = write(tmp_path, [receipt("c0", repeats=2)])
    a = asr_id.audit_receipts(p, MANIFEST, make_identity())
    assert a["decisions"]["c0"] == asr_id.R_MISSING_REPEATS
    assert "c0" in a["incomplete"]


def test_duplicate_candidate_fails(tmp_path):
    ident = make_identity()
    p = write(tmp_path, [receipt("c0", ident=ident), receipt("c0", ident=ident)])
    a = asr_id.audit_receipts(p, MANIFEST, ident)
    assert a["duplicate_candidate_ids"] == {"c0": 2}
    assert asr_id.R_DUPLICATE in a["fail_closed_hard_errors"]


def test_invalid_json_tail_quarantine(tmp_path):
    ident = make_identity()
    good = json.dumps(receipt("c0", ident=ident)) + "\n"
    p = tmp_path / "t.jsonl"
    p.write_text(good + '{"id": "c1", "brok' + "\n")
    a = asr_id.audit_receipts(p, MANIFEST, ident)
    assert len(a["invalid_tail_lines"]) == 1
    q = asr_id.quarantine_tail(p, a["valid_line_indices"])
    assert q.is_file() and p.read_text() == good
    a2 = asr_id.audit_receipts(p, MANIFEST, ident)
    assert a2["parsed_valid_lines"] == 1 and not a2["invalid_tail_lines"]


def test_manifest_missing_row_fails(tmp_path):
    p = write(tmp_path, [receipt("cX", audio="z" * 64)])
    a = asr_id.audit_receipts(p, MANIFEST, make_identity())
    assert a["decisions"]["cX"] == asr_id.R_MANIFEST_MISSING


def test_legacy_receipt_engine_version_still_checked(tmp_path):
    """RC5-era receipts without run_identity but with engine env must still be
    compared on the fields they carry (vllm version)."""
    r = receipt("c0")
    r.pop("run_identity")
    r["engine"] = {"vllm": "0.14.0"}
    r["transcript_receipt_sha256"] = asr_id.receipt_sha256(r)  # honest legacy hash
    p = write(tmp_path, [r])
    a = asr_id.audit_receipts(p, MANIFEST, make_identity())
    assert a["decisions"]["c0"] == asr_id.R_ENGINE_MISMATCH


def test_receipt_sha_binds_content():
    r1 = receipt("c0")
    r2 = receipt("c0")
    r2["repeats"][0]["text"] = "mutated"
    assert asr_id.receipt_sha256(r1) != asr_id.receipt_sha256(r2)
    assert r1["transcript_receipt_sha256"] == asr_id.receipt_sha256(r1)


# ---- scorer hardening (rc5_score_transcripts.validate_transcripts) ----

def _load_scorer():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rc5_score_transcripts", Path(__file__).resolve().parent.parent /
        "scripts/rc5_score_transcripts.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rc5_score_transcripts"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_scorer_rejects_duplicate(tmp_path):
    mod = _load_scorer()
    rows = [receipt("c0"), receipt("c0")]
    with pytest.raises(mod.ScorerValidationError, match="duplicate"):
        mod.validate_transcripts(rows, {r["id"]: r for r in MANIFEST}, 4, False)


def test_scorer_rejects_wrong_repeat_count(tmp_path):
    mod = _load_scorer()
    with pytest.raises(mod.ScorerValidationError, match="repeat count"):
        mod.validate_transcripts([receipt("c0", repeats=3)],
                                 {r["id"]: r for r in MANIFEST}, 4, False)


def test_scorer_rejects_inconsistent_repeat_counts():
    mod = _load_scorer()
    ref = {r["id"]: r for r in MANIFEST}
    with pytest.raises(mod.ScorerValidationError, match="inconsistent repeat"):
        mod.validate_transcripts([receipt("c0", repeats=4),
                                   receipt("c1", audio="b" * 64, repeats=2)], ref, None, False)


def test_scorer_rejects_audio_mismatch():
    mod = _load_scorer()
    with pytest.raises(mod.ScorerValidationError, match="audio changed"):
        mod.validate_transcripts([receipt("c0", audio="z" * 64)],
                                 {r["id"]: r for r in MANIFEST}, 4, False)


def test_scorer_rejects_missing_candidates_no_silent_skip():
    mod = _load_scorer()
    ref = {r["id"]: r for r in MANIFEST}
    with pytest.raises(mod.ScorerValidationError, match="missing from transcripts"):
        mod.validate_transcripts([receipt("c0")], ref, 4, False)


def test_scorer_rejects_cross_engine_mixing():
    mod = _load_scorer()
    ref = {r["id"]: r for r in MANIFEST}
    r0, r1 = receipt("c0"), receipt("c1", audio="b" * 64)
    r0["run_identity"] = make_identity(vllm="0.19.1")
    r1["run_identity"] = make_identity(vllm="0.14.0")
    with pytest.raises(mod.ScorerValidationError, match="cross-engine"):
        mod.validate_transcripts([r0, r1], ref, 4, False)


def test_scorer_rejects_unknown_id():
    mod = _load_scorer()
    with pytest.raises(mod.ScorerValidationError, match="not in the audio manifest"):
        mod.validate_transcripts([receipt("cX")], {r["id"]: r for r in MANIFEST}, 4, False)


def test_scorer_accepts_valid_partial_with_flag():
    mod = _load_scorer()
    ref = {r["id"]: r for r in MANIFEST}
    mod.validate_transcripts([receipt("c0")], ref, 4, True)  # no raise


def test_scorer_sdi_math():
    mod = _load_scorer()
    d = mod.sdi(list("abc"), list("abd"))
    assert d == {"substitutions": 1, "deletions": 0, "insertions": 0}
    d = mod.sdi(list("abc"), list("ab"))
    assert d["deletions"] == 1 and d["substitutions"] == 0
    d = mod.sdi(list("ab"), list("abc"))
    assert d["insertions"] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
