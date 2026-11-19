"""Fail-closed numeric evidence verification; synthetic, no WSB data."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_numeric_receipt_integrity as V


def row(id, ed=3):
    return {
        "id": id,
        "seed": 1,
        "metrics": {"per": {
            "edits": ed, "reference_phonemes": 123,
            "asr_repeats": [{"edits": 3, "text": "private synthetic"}],
            "reference_lyrics": "synthetic and private",
        }},
    }


def test_identical_numeric_receipts_pass():
    a = row("x")
    safe = row("x")
    del safe["metrics"]["per"]["asr_repeats"][0]["text"]
    del safe["metrics"]["per"]["reference_lyrics"]
    assert V.compare_pairs([a], [safe], "fixture") == []


def test_numerical_asr_repeat_drift_is_caught():
    a = row("x")
    b = row("x")
    b["metrics"]["per"]["asr_repeats"][0]["edits"] = 99
    assert any("numeric changed" in x for x in V.compare_pairs([a], [b], "fixture"))


def test_duplicate_id_fails_even_when_counts_match():
    a = [row("x"), row("y")]
    b = [row("x"), row("x")]
    assert any("duplicate" in x for x in V.compare_pairs(a, b, "fixture"))


def test_added_candidate_and_dropped_candidate_are_rejected():
    a = [row("x"), row("y")]
    b = [row("x"), row("z")]
    p = V.compare_pairs(a, b, "fixture")
    assert any("dropped" in x for x in p)
    assert any("added" in x for x in p)


def test_numeric_field_removed_even_from_snapshot_is_rejected():
    a = {".per": 0.2, ".asr_repeats[0].edits": 1}
    b = {".per": 0.2}
    assert any("dropped" in x for x in V.numeric_difference(a, b, "snapshot"))


def test_added_numeric_field_rejected():
    a = {".per": 0.2}
    b = {".per": 0.2, ".unreviewed": 42}
    assert any("added" in x for x in V.numeric_difference(a, b, "snapshot"))


def test_missing_identity_value_rejected():
    a = row("x")
    b = row("x")
    del b["seed"]
    assert any("identity seed" in x for x in V.compare_pairs([a], [b], "fixture"))


def test_float_integer_json_canonicalization_is_not_numeric_drift():
    assert V.numeric_difference({".per": 1.0, ".temp": 0.0},
                                {".per": 1, ".temp": 0}, "fixture") == []


def test_boolean_replaced_by_numeric_is_not_equivalent():
    problems = V.numeric_difference({".complete": True},
                                    {".complete": 1}, "fixture")
    assert any("changed" in p for p in problems)
