"""Reference-evaluator handoff must preserve selection and exclude dataset text."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_per_reference_package as H
from test_per_tail_analysis import dataset


def test_numeric_reference_record_cannot_publish_lyrics():
    raw = {"id": "wsb_001_r0_s8", "prompt_index": 1, "candidate_index": 0,
           "seed": 8, "audio_sha256": "abc", "lang": "en",
           "target": {"reference_lyrics": "secret-short"},
           "audio_path": "/restricted/audio.flac",
           "metrics": {"per": {"per": 0.1, "edits": 10,
                               "reference_phonemes": 100,
                               "asr_repeats": [{"text": "secret"}],
                               "reference_lyrics": "secret-short"}}}
    obj = H.restricted_per_numeric_record(raw)
    encoded = json.dumps(obj)
    assert "secret" not in encoded and "target" not in obj
    assert "audio_path" not in obj and "asr_repeats" not in encoded
    assert obj["metrics"]["per"]["edits"] == 10


def test_one_sample_bucket_never_reads_past_end(tmp_path):
    rows, summary = dataset()
    p = tmp_path / "per_song.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    selected = H.pick_stratified(p, tmp_path, summary, n_per_bucket=2)
    assert selected
    assert len({x["id"] for x in selected}) == len(selected)


def test_handoff_requires_true_official_summary(tmp_path):
    import pytest
    rows, summary = dataset()
    p = tmp_path / "per_song.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    bad = {"selected_candidates": summary["selected_candidates"][:2]}
    with pytest.raises(ValueError, match="192"):
        H.pick_stratified(p, tmp_path, bad)


def test_no_audio_is_copied_without_rights_flag():
    import subprocess
    r = subprocess.run([sys.executable,
        str(ROOT / "scripts" / "build_per_reference_package.py"),
        "--run", "/nonexistent", "--out", "/nonexistent/out"],
        capture_output=True, text=True)
    assert r.returncode != 0
    assert "rights clearance" in r.stderr
