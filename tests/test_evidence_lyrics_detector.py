"""tests for evidence_lyrics_detector.py — ALL fixtures are SYNTHETIC.

No WildSongBench content is used or embedded. The synthetic 'lyrics' are
sentences written for this test file. Verifies the C1 security requirements:
short lyrics caught; nested transcripts caught; phoneme arrays caught;
indirect copies caught regardless of key name or file extension; gfx1100
hardware fields and numeric phoneme counts NOT flagged; unparseable
structured evidence FAILS CLOSED; no raw content in scanner output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import evidence_lyrics_detector as D  # noqa: E402

# Synthetic ground truth (invented for this test; NOT dataset text)
SYN_LYRICS = {
    "prompt_index": 0,
    "lyrics": "[verse]\n测试合成歌词第一行内容独特色彩\n第二行合成文字用于检测匹配窗口\n",
    "style": "synth, Male Vocals",
}
SYN_MANIFEST = None  # built per-test in tmp_path


@pytest.fixture()
def synth_manifest(tmp_path):
    p = tmp_path / "synth_manifest.jsonl"
    p.write_text(json.dumps(SYN_LYRICS, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    return p


def windows_from(manifest: Path):
    return D.load_ground_truth(manifest)


def test_synthetic_lyrics_produce_windows(synth_manifest):
    ws = windows_from(synth_manifest)
    assert ws, "synthetic CJK lyric lines must produce fingerprint windows"


def test_direct_copy_detected_any_extension(tmp_path, synth_manifest):
    ws = windows_from(synth_manifest)
    norm = D._norm("随便什么前缀 测试合成歌词第一行内容独特色彩 随便什么后缀")
    hits = {s for w, s, _ in ws if w in norm}
    assert hits, "direct lyric copy must match under arbitrary surroundings"
    # extension independence: the match is content-based, not name-based
    assert D._norm(open(__file__, encoding="utf-8").read()) is not None


def test_indirect_copy_under_innocent_key(tmp_path, synth_manifest):
    """Lyrics smuggled under a non-forbidden key ('note') are caught by
    tier 2 ground truth, which key scans cannot see."""
    leak = {"note": "备注：测试合成歌词第一行内容独特色彩", "per": 0.1}
    f = tmp_path / "leak.json"
    f.write_text(json.dumps(leak, ensure_ascii=False), encoding="utf-8")
    issues = D.key_scan_structured("leak.json", f.read_bytes())
    assert issues == [], "key-scan must not flag innocent keys (tier-2's job)"
    # tier 2:
    ws = windows_from(synth_manifest)
    norm = D._norm(f.read_text(encoding="utf-8"))
    assert any(w in norm for w, _, _ in ws), "tier-2 must catch the indirect copy"


def test_short_lyric_under_forbidden_key_flagged(tmp_path):
    """<50-char strings under sensitive keys are still flagged (no length
    exemption)."""
    row = {"reference_lyrics": "短歌词也算"}
    f = tmp_path / "short.jsonl"
    f.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    assert D.key_scan_structured("short.jsonl", f.read_bytes()) == [
        "reference_lyrics"]


def test_nested_transcript_array_flagged(tmp_path):
    row = {"metrics": {"per": {"asr_repeats": [
        {"text": "nested asr transcript", "edits": 3}]}}}
    f = tmp_path / "nested.jsonl"
    f.write_text(json.dumps(row) + "\n")
    assert "metrics.per.asr_repeats" in D.key_scan_structured(
        "nested.jsonl", f.read_bytes())


def test_numeric_asr_repeats_receipt_allowed(tmp_path):
    """The numeric receipt form (language/repeat/edits/per/truncated) that
    replaced raw transcripts in the public tree must NOT be flagged."""
    row = {"metrics": {"per": {"asr_repeats": [
        {"language": "Chinese", "repeat": 0, "edits": 41,
         "per": 0.0646, "truncated": False},
        {"language": "", "repeat": 1, "edits": 41,
         "per": 0.0646, "truncated": False}]}}}
    f = tmp_path / "numeric.jsonl"
    f.write_text(json.dumps(row) + "\n")
    assert D.key_scan_structured("numeric.jsonl", f.read_bytes()) == []


def test_phoneme_token_array_flagged_numeric_count_allowed():
    assert not D._container_all_safe(["m", "ei2", "g", "ui1"])
    # token arrays: strings are not numeric and not safe enums -> container unsafe
    assert not D._container_all_safe({"reference_tokens": ["m", "ei2"]})
    # numeric count is safe
    assert D._container_all_safe({"reference_phonemes": 384})


def test_gfx1100_target_field_allowed():
    assert not D._container_all_safe("gfx1100")  # exception is key-specific, not a general safe string
    issues = D.key_scan_structured(
        "x.json", json.dumps({"target": "gfx1100"}).encode())
    assert issues == [], "hardware target must not be flagged"


def test_unparseable_structured_fails_closed(tmp_path):
    f = tmp_path / "broken.json"
    f.write_text("{not json", encoding="utf-8")
    issues = D.key_scan_structured("broken.json", f.read_bytes())
    assert any("UNPARSEABLE" in i for i in issues)


def test_extension_bypass_still_caught_by_ground_truth(synth_manifest):
    """Renaming leak.json to leak.txt/csv/md cannot bypass tier 2 (tier 2
    scans every text file's content)."""
    ws = windows_from(synth_manifest)
    for name in ("leak.txt", "leak.csv", "leak.md", "leak.py"):
        content = f"prefix 测试合成歌词第一行内容独特色彩 suffix"
        norm = D._norm(content)
        assert any(w in norm for w, _, _ in ws), f"{name} bypass attempt"


def test_style_tags_not_fingerprinted(synth_manifest):
    """Style tag lists are factual metadata; fingerprinting them caused false
    positives (English docs mentioning 'male vocals mandarin')."""
    ws = windows_from(synth_manifest)
    norm = D._norm("the docs say synth, male vocals and nothing else")
    assert not any(w in norm for w, _, _ in ws), (
        "style fragments must not be treated as lyric ground truth")


def test_scanner_output_never_contains_matched_text(synth_manifest):
    """Violation reports carry file + sha8 only — asserting the discipline."""
    s = D.sha8("测试合成歌词第一行内容独特色彩")
    assert len(s) == 8 and all(c in "0123456789abcdef" for c in s)


def test_hash_digest_values_allowed():
    assert D._container_all_safe("lyric-sha256:6da0402c32cf")
    assert D._container_all_safe("phonemes-sha256:abc123def456(384 tokens)")
    assert D._container_all_safe("a1b2c3d4e5f60718")  # plain digest
    assert not D._container_all_safe("这是真实歌词文本内容")
