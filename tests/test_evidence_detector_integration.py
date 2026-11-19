"""End-to-end tier-2 exercise with ORIGINAL SYNTHETIC lyrics only.

Never download or commit WildSongBench manifests. Real licensed-manifest audit
must run separately on a rights-cleared host with --require-ground-truth.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import evidence_lyrics_detector as D

SYNTH = "The copper fireflies drift beyond our floating paper lighthouse"


def test_english_ground_truth_produces_distinctive_windows(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"lyrics": SYNTH}) + "\n")
    windows = D.load_ground_truth(manifest)
    assert windows
    assert all(len(window) >= 32 for window, _, _ in windows)
    assert any(window in D._norm(SYNTH) for window, _, _ in windows)


def test_release_mode_requires_verified_manifest(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["detector", "--manifest",
                                     str(tmp_path / "missing.jsonl"),
                                     "--require-ground-truth"])
    assert D.main() == 2
    captured = capsys.readouterr()
    assert "NOT TESTED" in captured.err


def test_synthetic_tier2_end_to_end_and_no_lyric_logs(
        tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    manifest = tmp_path / "private-synthetic-manifest.jsonl"
    manifest.write_text(json.dumps({"lyrics": SYNTH}) + "\n")
    expected_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    leak = tmp_path / "sample.notes"  # obscure extension and non-forbidden key
    leak.write_text("Unrelated note: " + SYNTH)
    safe = tmp_path / "safe.jsonl"
    safe.write_text(json.dumps({"value": 0.42}) + "\n")
    subprocess.run(["git", "add", "sample.notes", "safe.jsonl"],
                   cwd=tmp_path, check=True)
    monkeypatch.setattr(D, "ROOT", tmp_path)
    monkeypatch.setattr(D, "MANIFEST_SHA", expected_sha)
    monkeypatch.setattr(sys, "argv", ["detector", "--manifest",
                                     str(manifest), "--require-ground-truth"])
    assert D.main() == 1  # real matched content under an unknown extension
    capture = capsys.readouterr()
    assert "sha8=" in capture.err
    assert SYNTH not in capture.err
    leak.write_text("Only independent, safe scientific notes.")
    assert D.main() == 0
    output = capsys.readouterr()
    assert "tier2=on" in output.out
    assert SYNTH not in output.out


def test_failure_to_read_tracked_file_is_not_silently_skipped(
        tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    p = tmp_path / "sample.jsonl"
    p.write_text('{"safe": 4}\n')
    subprocess.run(["git", "add", "sample.jsonl"], cwd=tmp_path, check=True)
    monkeypatch.setattr(D, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["detector", "--manifest",
                                     str(tmp_path / "missing")])
    original = Path.read_bytes

    def fail_selected(self):
        if self == p:
            raise OSError("synthetic inaccessible file")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", fail_selected)
    assert D.main() == 2
    captured = capsys.readouterr()
    assert "unreadable tracked evidence" in captured.err
    assert "synthetic inaccessible file" not in captured.err


def test_csv_quoted_sensitive_column_flagged():
    payload = b'"candidate,id","reference_lyrics","score"\n"a,b","private",0.1\n'
    issues = D.key_scan_structured("scores.csv", payload)
    assert "csv-column:1" in issues


def test_csv_malformed_quote_fails_closed():
    payload = b'candidate,score\n"unfinished quote,0.2\n'
    issues = D.key_scan_structured("scores.csv", payload)
    assert "UNPARSEABLE-CSV" in issues
