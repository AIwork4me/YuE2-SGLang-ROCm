"""Security redaction controls — synthetic data only, no WSB lyrics."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import redact_evidence as R


def test_short_lyrics_cannot_escape_public_export():
    original = {"target": {"reference_lyrics": "abc"},
                "metrics": {"per": {"text": "few", "phonemes": ["a", "b"],
                                    "per": 0.125, "reference_phonemes": 12}}}
    out = R.redact_obj(original)
    assert "target" not in out
    assert "text" not in out["metrics"]["per"]
    assert "phonemes" not in out["metrics"]["per"]
    assert out["metrics"]["per"]["reference_phonemes"] == 12
    assert out["metrics"]["per"]["per"] == 0.125


def test_numeric_evidence_is_preserved():
    original = {"records": [{"metrics": {"per": {"reference_phonemes": 634,
                                                  "edits": 14, "per": 14 / 634}}},
                            {"metrics": {"per": {"edits": 50}}}],
                "target": "gfx1100 (Radeon)"}
    clean = R.redact_obj(original)
    assert dict(R.numeric_leaves(clean)) == dict(R.numeric_leaves(original))
    assert clean["target"].startswith("gfx")


def test_redacted_file_round_trip(tmp_path):
    import json
    raw = tmp_path / "private.jsonl"
    raw.write_text(json.dumps({"metrics": {"per": {"per": 0.1, "text": "short"}}}) + "\n")
    public = R.redact_file(raw)
    assert public.name == "private.redacted.jsonl"
    assert R.verify(public, raw)
    assert "short" not in public.read_text()
    assert raw.read_text().endswith("short\"}}\n")


def test_preexisting_export_not_overwritten(tmp_path):
    import json
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"text": "private"}))
    public = R.redact_file(path)
    assert public.is_file()
    import pytest
    with pytest.raises(FileExistsError):
        R.redact_file(path)
