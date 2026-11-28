#!/usr/bin/env python3
"""RED tests for RC6.1 M2 — ASR evaluator identity & durable resume.

Encodes the DESIRED fail-closed behaviour for the 12 residual defects
statically identified in the mission (rc6_asr_identity.py,
rc5_asr_vllm_native.py, rc5_score_transcripts.py). Against the RC6.1-pre
code most of these FAIL (RED evidence); after the fix they must pass.

Fully offline synthetic fixtures — no models, no GPU, no audio files.

Run:  python3 -m pytest tests/test_rc61_asr_identity.py -v
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
     "audio_path": "/nonexistent/a0.wav", "audio_sha256": "a" * 64},
    {"id": "c1", "prompt_index": 0, "candidate_index": 1, "lang": "en",
     "audio_path": "/nonexistent/a1.wav", "audio_sha256": "b" * 64},
    {"id": "c2", "prompt_index": 1, "candidate_index": 0, "lang": "zh",
     "audio_path": "/nonexistent/a2.wav", "audio_sha256": "c" * 64},
]


def make_identity(**over):
    ident = {
        "schema": asr_id.SCHEMA,
        "model": {"root": "/x", "snapshot": "snap", "files": {"f": "m" * 64},
                  "files_sha256": "m" * 64},
        "engine": {"engine": "vLLM native", "engine_class": "vllm.LLM",
                   "vllm": "0.19.1", "torch": "2.10.0+rocm7.12.0",
                   "hip": "7.12.6", "dtype": "bfloat16", "seed": 0},
        "audio_preprocessing": {"audio_loading": "normalize_audios",
                                "chunking": "split_audio_into_chunks",
                                "utils_sha256": "u" * 64, "sample_rate": 16000},
        "decoding": {"temperature": 0.0, "top_p": 1.0, "top_k": -1,
                     "max_tokens": 4096, "seed": 0, "repeats": 4,
                     "batch_songs": 4},
        "scoring": {"audio_manifest_sha256": "s" * 64},
        "driver": {"path": "/d.py", "sha256": "d" * 64},
    }
    ident.update(over)
    ident["run_identity_sha256"] = asr_id.sha256_bytes(
        json.dumps({k: v for k, v in ident.items() if k != "run_identity_sha256"},
                   sort_keys=True, ensure_ascii=False).encode())
    return ident


def receipt(cid="c0", audio="a" * 64, repeats=4, ident=None, status="complete",
            extra=None):
    r = {"id": cid, "prompt_index": 0, "candidate_index": 0, "lang": "en",
         "audio_sha256": audio, "chunks": 1,
         "repeats": [{"repeat": i, "text": "x"} for i in range(repeats)],
         "engine": {}, "run_identity": ident if ident is not None else make_identity(),
         "repeat_count": repeats, "status": status}
    if extra:
        r.update(extra)
    r["transcript_receipt_sha256"] = asr_id.receipt_sha256(r)
    return r


def write(tmp_path, rows, name="t.jsonl"):
    p = tmp_path / name
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


# ------------------------------------------------- D1: full identity binding
def test_D1_identity_change_outside_compared_fields_is_rejected(tmp_path):
    """Defect: audit_receipts compares only a subset of identity fields — a
    change in e.g. preprocessing/scoring/driver passes as REUSABLE."""
    ident = make_identity()
    changed = make_identity()
    changed["audio_preprocessing"]["utils_sha256"] = "z" * 64
    changed["run_identity_sha256"] = asr_id.sha256_bytes(
        json.dumps({k: v for k, v in changed.items() if k != "run_identity_sha256"},
                   sort_keys=True, ensure_ascii=False).encode())
    p = write(tmp_path, [receipt(ident=changed)])
    audit = asr_id.audit_receipts(p, MANIFEST, run_identity=ident, expected_repeats=4)
    assert audit["decisions"]["c0"] not in (asr_id.R_OK,), audit
    assert audit["decisions"]["c0"].startswith("REJECT")


def test_D2_receipt_hash_not_recomputed_tamper_detected(tmp_path):
    """Defect: transcript content mutated while transcript_receipt_sha256
    stays stale is accepted as REUSABLE."""
    r = receipt()
    r["repeats"][0]["text"] = "TAMPERED"          # content changed...
    # ...hash NOT recomputed (stale)
    p = write(tmp_path, [r])
    audit = asr_id.audit_receipts(p, MANIFEST, run_identity=make_identity(),
                                  expected_repeats=4)
    assert audit["decisions"]["c0"] != asr_id.R_OK, audit
    assert "HASH" in audit["decisions"]["c0"] or "TAMPER" in audit["decisions"]["c0"]


def test_D3_missing_decoding_fields_fail_closed(tmp_path):
    ident = make_identity()
    cur = make_identity()
    cur["decoding"].pop("temperature")              # key absent in receipt identity
    cur["run_identity_sha256"] = asr_id.sha256_bytes(
        json.dumps({k: v for k, v in cur.items() if k != "run_identity_sha256"},
                   sort_keys=True, ensure_ascii=False).encode())
    p = write(tmp_path, [receipt(ident=ident)])
    audit = asr_id.audit_receipts(p, MANIFEST, run_identity=cur, expected_repeats=4)
    assert audit["decisions"]["c0"] != asr_id.R_OK, audit


def test_D4_legacy_partial_identity_not_strict_reusable(tmp_path):
    """Defect: receipts without run_identity (legacy) can be REUSABLE when
    only the vllm version happens to match."""
    r = receipt()
    r.pop("run_identity")                           # legacy shape
    r["engine"] = {"vllm": "0.19.1"}
    r["transcript_receipt_sha256"] = asr_id.receipt_sha256(r)  # honest legacy hash
    p = write(tmp_path, [r])
    audit = asr_id.audit_receipts(p, MANIFEST, run_identity=make_identity(),
                                  expected_repeats=4)
    assert audit["decisions"]["c0"] != asr_id.R_OK, audit
    assert audit["decisions"]["c0"] == "HISTORICAL_RECEIPT_VALID_IDENTITY_PARTIAL" \
        or audit["decisions"]["c0"].startswith("REJECT")


def test_D5_extra_repeats_rejected(tmp_path):
    """Defect: len(reps) > expected accepted (only fewer was checked)."""
    r = receipt(repeats=6)                          # expected 4
    p = write(tmp_path, [r])
    audit = asr_id.audit_receipts(p, MANIFEST, run_identity=make_identity(),
                                  expected_repeats=4)
    assert audit["decisions"]["c0"] != asr_id.R_OK, audit


def test_D6_midfile_corruption_is_not_a_repairable_tail(tmp_path):
    """Defect: malformed lines anywhere are dropped as a repairable 'tail'."""
    good = [receipt(cid="c0"), receipt(cid="c1", audio="b" * 64)]
    raw = json.dumps(good[0]) + "\n{broken json\n" + json.dumps(good[1]) + "\n"
    p = tmp_path / "t.jsonl"
    p.write_text(raw)
    audit = asr_id.audit_receipts(p, MANIFEST, run_identity=make_identity(),
                                  expected_repeats=4)
    # mid-file corruption must NOT be classified as a repairable tail
    assert audit["fail_closed_hard_errors"], audit
    assert not audit["resume_allowed"], audit


def test_D6b_true_tail_corruption_is_quarantinable(tmp_path):
    """A torn LAST line (crash mid-append) is still a repairable tail."""
    good = [receipt(cid="c0"), receipt(cid="c1", audio="b" * 64)]
    raw = json.dumps(good[0]) + "\n" + json.dumps(good[1]) + "\n{torn"
    p = tmp_path / "t.jsonl"
    p.write_text(raw)
    audit = asr_id.audit_receipts(p, MANIFEST, run_identity=make_identity(),
                                  expected_repeats=4)
    assert audit["invalid_tail_lines"] and len(audit["invalid_tail_lines"]) == 1
    assert audit["fail_closed_hard_errors"] == [], audit
    assert audit["resume_allowed"], audit


def test_D7_manifest_duplicate_ids_detected(tmp_path):
    """Defect: manifest duplicate ids silently overwrite in the dict build."""
    dup_manifest = MANIFEST + [dict(MANIFEST[1], audio_sha256="z" * 64)]
    p = write(tmp_path, [receipt(cid="c1", audio="z" * 64)])
    audit = asr_id.audit_receipts(p, dup_manifest, run_identity=make_identity(),
                                  expected_repeats=4)
    assert audit["fail_closed_hard_errors"], audit
    assert not audit["resume_allowed"], audit


def test_D8_quarantine_preserves_original_and_is_atomic(tmp_path):
    good = [receipt(cid="c0"), receipt(cid="c1", audio="b" * 64)]
    raw = json.dumps(good[0]) + "\n" + json.dumps(good[1]) + "\n{torn"
    p = tmp_path / "t.jsonl"
    p.write_text(raw)
    audit = asr_id.audit_receipts(p, MANIFEST, run_identity=make_identity(),
                                  expected_repeats=4)
    q = asr_id.quarantine_tail(p, audit["valid_line_indices"])
    assert q.is_file()
    assert "{torn" in q.read_text()                # original fully preserved
    lines = [l for l in p.read_text().splitlines() if l.strip()]
    assert len(lines) == 2 and all(json.loads(l)["id"] in ("c0", "c1") for l in lines)
    # no temp litter left behind
    assert not list(tmp_path.glob("*.tmp*"))


# ------------------------------------------------- D9: supersede on resume
def test_D9_incomplete_receipts_are_superseded_not_duplicated(tmp_path):
    """Defect: re-running an incomplete candidate appends a duplicate id.
    prepare_resume() must move incomplete rows to a superseded file first."""
    incomplete = receipt(cid="c2", audio="c" * 64, repeats=2)   # expected 4
    p = write(tmp_path, [receipt(cid="c0"), receipt(cid="c1", audio="b" * 64),
                         incomplete])
    res = asr_id.prepare_resume(p, MANIFEST, run_identity=make_identity(),
                                expected_repeats=4)
    ids = [json.loads(l)["id"] for l in p.read_text().splitlines() if l.strip()]
    assert ids.count("c2") == 0, ids                # incomplete row superseded away
    assert res["todo"] == ["c2"]
    sup = Path(res["superseded_file"])
    assert sup.is_file()
    sup_ids = [json.loads(l)["id"] for l in sup.read_text().splitlines() if l.strip()]
    assert "c2" in sup_ids


def test_D10_strict_pairing_no_silent_truncation():
    """Defect: zip(owner, outputs) / zip(batch, wavs) silently truncate."""
    with pytest.raises(ValueError):
        asr_id.pair_strict([1, 2, 3], [1, 2])
    assert asr_id.pair_strict(["a", "b"], [1, 2]) == [("a", 1), ("b", 2)]


# ------------------------------------------------- D11: scorer audio binding
def test_D11_scorer_detects_manifest_audio_hash_mismatch(tmp_path):
    """Defect: scorer compares only DECLARED hashes (transcripts vs
    manifest); the actual file on disk is never verified."""
    real = tmp_path / "a0.wav"
    real.write_bytes(b"REAL AUDIO BYTES")
    import hashlib
    true_sha = hashlib.sha256(real.read_bytes()).hexdigest()
    manifest = [dict(MANIFEST[0], audio_path=str(real), audio_sha256="0" * 64)]
    problems = asr_id.verify_audio_files(manifest)
    assert problems and problems[0]["id"] == "c0" and problems[0]["actual"] == true_sha
    assert problems[0]["declared"] == "0" * 64


def test_D11b_scorer_audio_verification_ok(tmp_path):
    real = tmp_path / "a0.wav"
    real.write_bytes(b"REAL AUDIO BYTES")
    import hashlib
    manifest = [dict(MANIFEST[0], audio_path=str(real),
                     audio_sha256=hashlib.sha256(real.read_bytes()).hexdigest())]
    assert asr_id.verify_audio_files(manifest) == []


# ------------------------------------------------- D12: canonical identity
def test_D12_canonical_identity_includes_processor_prompt_chunking():
    ident = asr_id.build_canonical_identity(
        model_root=None, model_files={"f": "m" * 64},
        engine={"engine": "e", "vllm": "v", "torch": "t", "hip": "h", "dtype": "d",
                "seed": 0},
        preproc={"audio_loading": "l", "chunking": "c", "utils_sha256": "u" * 64,
                 "sample_rate": 16000, "max_chunk_sec": 1200},
        prompt_template="CHAT_TEMPLATE_HASH_OR_TEXT",
        processor_files={"processor_config.json": "p" * 64},
        decoding={"temperature": 0.0, "max_tokens": 4096, "repeats": 4,
                  "seed": 0, "batch_songs": 4},
        scoring={"audio_manifest_sha256": "s" * 64},
        driver_sha256="d" * 64)
    sci = ident["scientific_content_identity"]
    assert "processor" in sci and sci["processor"]["files"]["processor_config.json"] == "p" * 64
    assert sci["prompt_template_sha256"]
    assert sci["audio_preprocessing"]["max_chunk_sec"] == 1200
    assert "execution_provenance" in ident
    # machine-specific paths live in execution provenance, NOT in the hash
    blob = json.dumps(sci, sort_keys=True)
    assert "/x/" not in blob and "/data/" not in blob


def test_D12b_missing_critical_identity_fields_refused():
    with pytest.raises(ValueError):
        asr_id.build_canonical_identity(
            model_root=None, model_files={},                     # empty -> refuse
            engine={"engine": "e", "vllm": "v"},
            preproc={}, prompt_template=None, processor_files=None,
            decoding={"repeats": 4}, scoring={}, driver_sha256=None)
