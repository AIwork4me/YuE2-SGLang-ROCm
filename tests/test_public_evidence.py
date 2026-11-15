"""Public evidence must not contain raw lyrics or ASR transcriptions."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("public_evidence_guard", ROOT / "scripts" / "public_evidence_guard.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_detects_nested_reference_lyrics_without_values():
    obj = {"metrics": {"per": {"reference_lyrics": "private", "per": 0.12}}}
    issues = list(guard.sensitive_paths(obj))
    assert issues == ["metrics.per.reference_lyrics"]
    assert "private" not in repr(issues)


def test_detects_asr_raw_chunks():
    obj = {"metrics": {"per": {"asr_repeats": [{"raw_chunks": [{"text": "private"}]}]}}}
    assert list(guard.sensitive_paths(obj)) == ["metrics.per.asr_repeats[0].raw_chunks"]


def test_allows_numeric_receipts(tmp_path):
    p = tmp_path / "test.jsonl"
    p.write_text(json.dumps({"id": "wsb_001", "metrics": {"per": {"per": 0.12, "edits": 12}}}) + "\n")
    assert list(guard.inspect_file(p)) == []


def test_hardware_target_and_numeric_phoneme_count_are_not_lyrics():
    obj = {"target": "gfx1100 (AMD Radeon PRO W7900)", "phonemes": 240}
    assert list(guard.sensitive_paths(obj)) == []


def test_target_object_and_text_phonemes_are_rejected():
    obj = {"target": {"reference_lyrics": "private"},
           "phonemes": ["p", "r", "i", "v", "a", "t", "e"]}
    assert list(guard.sensitive_paths(obj)) == ["target", "phonemes"]
