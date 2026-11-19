"""C2 P1 — evidence-based sample classification: negative controls.

All fixtures synthetic. Proves: PER value NEVER determines empty state;
EMPTY_CONFIRMED requires direct transcript evidence with a verifiable receipt;
labels cross; conservation is fail-closed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from sample_classification import (  # noqa: E402
    EMPTY_CONFIRMED, EMPTY_UNKNOWN, NONEMPTY_CONFIRMED,
    assert_conservation, empty_state, labels)


def row(lang="en", **per):
    base = {"per": 0.1, "edits": 10, "reference_phonemes": 100}
    base.update(per)
    return {"id": "wsb_000_r0_s1", "prompt_index": 0, "candidate_index": 0,
            "seed": 1, "lang": lang,
            "metrics": {"per": base}}


def test_per_one_nonempty_transcript_is_NONEMPTY_CONFIRMED():
    r = row(per=1.0, edits=100, asr_repeats=[{"text": "fully wrong but audible"}],
            selected_asr_repeat=0)
    state, ev = empty_state(r)
    assert state == NONEMPTY_CONFIRMED
    assert ev["transcript_len"] == len("fully wrong but audible")


def test_per_one_empty_transcript_is_EMPTY_CONFIRMED_with_receipt():
    r = row(per=1.0, edits=100, asr_repeats=[{"text": "   "}],
            selected_asr_repeat=0)
    state, ev = empty_state(r)
    assert state == EMPTY_CONFIRMED
    assert len(ev["transcript_sha256"]) == 64  # restricted-original checkable


def test_per_one_redacted_transcript_is_EMPTY_UNKNOWN():
    r = row(per=1.0, edits=100)  # numeric-only receipt: no asr_repeats text
    state, ev = empty_state(r)
    assert state == EMPTY_UNKNOWN
    assert "transcript_sha256" not in ev


def test_per_zero_nonempty():
    r = row(per=0.0, edits=0, asr_repeats=[{"text": "perfect"}],
            selected_asr_repeat=0)
    assert empty_state(r)[0] == NONEMPTY_CONFIRMED


def test_per_above_one_is_not_a_special_case():
    r = row(per=1.4, edits=140, asr_repeats=[{"text": "insertion-heavy"}],
            selected_asr_repeat=0)
    assert empty_state(r)[0] == NONEMPTY_CONFIRMED


def test_asr_truncated_label_and_crossing():
    r = row(per=0.5, selected_asr_truncated=True, lang="zh")
    ls = labels(r)
    assert "ASR_CAPPED" in ls and "HIGH_PER" in ls and "LANG_ZH" in ls


def test_missing_language_is_LANG_UNKNOWN_not_false():
    r = row()
    del r["lang"]
    assert "LANG_UNKNOWN" in labels(r)


def test_selected_asr_repeat_out_of_range_fails_closed():
    r = row(asr_repeats=[{"text": "x"}], selected_asr_repeat=5)
    with pytest.raises(ValueError, match="out of range"):
        empty_state(r)


def test_repeat_entries_without_text_are_unknown():
    r = row(asr_repeats=[{"edits": 3}], selected_asr_repeat=0)
    assert empty_state(r)[0] == EMPTY_UNKNOWN


def full_dataset(selected_ci=0):
    rows = []
    chosen = []
    for i in range(192):
        for ci in (0, 1):
            rows.append({"id": f"wsb_{i:03d}_r{ci}_s{9000+i+ci}",
                         "prompt_index": i, "candidate_index": ci,
                         "seed": 9000 + i + ci,
                         "metrics": {"per": {"per": 0.1 * (ci + 1),
                                             "edits": 10 * (ci + 1),
                                             "reference_phonemes": 100}}})
        chosen.append({"prompt_index": i, "candidate_index": selected_ci})
    return rows, chosen


def test_conservation_holds_on_valid_dataset():
    rows, chosen = full_dataset()
    receipt = assert_conservation(rows, chosen)
    assert receipt == {"candidates": 384, "prompts": 192, "selected": 192,
                       "unselected": 192,
                       "shape": "192x2, one selected per prompt"}


def test_conservation_failures():
    rows, chosen = full_dataset()
    with pytest.raises(ValueError, match="384"):
        assert_conservation(rows[:-1], chosen)
    dup = [dict(r) for r in rows]
    dup[100] = dict(rows[0])  # same id twice, still 384 rows
    with pytest.raises(ValueError, match="duplicate"):
        assert_conservation(dup, chosen)
    bad_sel = chosen[:-1]
    with pytest.raises(ValueError, match="192"):
        assert_conservation(rows, bad_sel)
    two_same_prompt = [dict(c) for c in chosen]
    two_same_prompt[5] = dict(two_same_prompt[4])
    with pytest.raises(ValueError, match="duplicate coordinates|one candidate per prompt"):
        assert_conservation(rows, two_same_prompt)


def test_evidence_source_sha_is_carried_not_trusted():
    """source_sha is recorded for later cross-check; it never creates a
    CONFIRMED verdict by itself."""
    r = row(per=1.0, edits=100)  # no transcript
    state, ev = empty_state(r, source_sha="a" * 64)
    assert state == EMPTY_UNKNOWN
    assert ev["source_sha256"] == "a" * 64


def test_json_serializable_receipts():
    r = row(per=1.0, asr_repeats=[{"text": ""}], selected_asr_repeat=0)
    _, ev = empty_state(r)
    json.dumps(ev)  # receipts must be storable
