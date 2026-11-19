"""PER scientific controls: exact candidate selection and disjoint tails."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import per_tail_analysis as P


def dataset():
    rows, chosen = [], []
    for i in range(192):
        for ci in range(2):
            # Candidate 0 has true PER=0; 'per or 1' must never poison selection.
            per = 0.0 if ci == 0 else .2
            edits = 0 if ci == 0 else 20
            rows.append({
                "id": f"wsb_{i:03d}_r{ci}_s{8000 + i + ci}",
                "prompt_index": i, "candidate_index": ci, "seed": 8000 + i + ci,
                "audio_sha256": f"hash-{i}-{ci}", "lang": "en",
                "metrics": {"per": {"per": per, "edits": edits,
                                     "reference_phonemes": 100,
                                     "selected_asr_truncated": False}}
            })
        chosen.append({"prompt_index": i, "candidate_index": 0,
                       "seed": 8000 + i, "audio_sha256": f"hash-{i}-0"})
    return rows, {"selected_candidates": chosen}


def test_zero_per_is_selected_without_truthiness_bug():
    selected, other, prov, _audit = P.choose_rows(*((dataset()[0],)))
    assert len(selected) == 192
    assert all(r["candidate_index"] == 0 for r in selected)
    assert prov == "DIAGNOSTIC_MIN_PER_ONLY_NOT_OFFICIAL"


def test_official_selection_verifies_sha_and_seed():
    rows, summary = dataset()
    selected, other, prov, audit = P.choose_rows(rows, summary)
    assert prov == "OFFICIAL_SELECTION_AUDIO_IDENTITY_VERIFIED"
    assert audit["seed_verified"] == 192 and audit["audio_sha256_verified"] == 192
    summary["selected_candidates"][0]["audio_sha256"] = "incorrect"
    with pytest.raises(ValueError, match="audio_sha256"):
        P.choose_rows(rows, summary)


def test_ties_must_not_guess_official_tie_break():
    rows, summary = dataset()
    rows[1]["metrics"]["per"]["per"] = 0.0
    rows[1]["metrics"]["per"]["edits"] = 0
    with pytest.raises(ValueError, match="tie"):
        P.choose_rows(rows)
    assert len(P.choose_rows(rows, summary)[0]) == 192


def test_per_one_does_not_imply_empty_transcript():
    row = dataset()[0][1]
    row["metrics"]["per"]["per"] = 1.
    row["metrics"]["per"]["edits"] = 100
    assert P.per_fields(row)["empty"] is None  # redacted source
    row["metrics"]["per"].update(asr_repeats=[{"text": "vocals audible"}],
                                  selected_asr_repeat=0)
    assert P.per_fields(row)["empty"] is False
    row["metrics"]["per"]["asr_repeats"][0]["text"] = ""
    assert P.per_fields(row)["empty"] is True


def test_disjoint_partition_sums_to_selected_aggregate(tmp_path):
    rows, summary = dataset()
    p = tmp_path / "per_song.jsonl"
    p.write_text("".join(json.dumps(row) + "\n" for row in rows))
    s = tmp_path / "summary.json"
    s.write_text(json.dumps(summary))
    d = P.analyze(p, s, bootstrap=20)
    assert d["publication_grade_selection"]
    assert d["populations"]["selected_192"]["candidates"] == 192
    assert d["populations"]["selected_192"]["micro_per"] == 0.
    groups = d["selected_disjoint_capped_x_empty"]
    assert sum(z["candidates"] for z in groups.values()) == 192
    assert sum(z["edits"] for z in groups.values()) == 0
    assert groups["capped=False,empty=None"]["candidates"] == 192


def test_missing_candidate_fails_closed():
    rows, summary = dataset()
    with pytest.raises(ValueError, match="384"):
        P.choose_rows(rows[:-1], summary)
