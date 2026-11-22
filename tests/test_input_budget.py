"""input_budget.py + rc4_reliability_matrix.py regression tests (RC4.1 M3)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "input_budget_mod", REPO / "scripts" / "input_budget.py")
ib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ib)

spec2 = importlib.util.spec_from_file_location(
    "rc4_matrix_mod", REPO / "scripts" / "rc4_reliability_matrix.py")
mx = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(mx)


def test_repeated_tags_rejected_bounded():
    r = ib.check_payload(mx.REPEATED_TAGS_PAYLOAD)
    assert r["class"] == "STYLE_DEGENERATE_REPETITION"
    assert r["ok"] is False
    assert r["measured"]["style_sections"] == 200


def test_normal_tags_pass():
    r = ib.check_payload({"style": "[Tags]\nsoft pop, female vocal\n",
                          "lyrics": "[Lyrics]\nA tiny phrase.\n",
                          "seed": 1})
    assert r["ok"] is True and r["class"] == "OK"


def test_legal_repeated_tag_values_pass():
    """Legal repeated tag VALUES (not sections) must not be rejected."""
    style = "[Tags]\n" + "pop\n" * 30
    r = ib.check_payload({"style": style, "lyrics": "[Lyrics]\nA.\n"})
    assert r["ok"] is True


def test_multi_section_legal_style_pass():
    style = "[Tags]\npop\n[Mood]\nhappy\n[Genre]\ndance\n"
    r = ib.check_payload({"style": style, "lyrics": "[Lyrics]\nA.\n"})
    assert r["ok"] is True
    assert r["measured"]["style_sections"] == 3


def test_legal_long_lyrics_pass():
    lyrics = "[Lyrics]\n" + "\n".join(
        f"[verse {i}]\nLa la test phrase number {i} keeps going on\n" * 4
        for i in range(40))
    r = ib.check_payload({"style": "[Tags]\nsoft pop\n", "lyrics": lyrics})
    assert r["ok"] is True
    assert r["measured"]["lyrics_bytes"] < 65536


def test_oversized_style_rejected():
    r = ib.check_payload({"style": "x" * 2_000_000, "lyrics": "[Lyrics]\nA.\n"})
    assert r["class"] == "STYLE_TOO_LARGE"
    assert r["ok"] is False


def test_type_errors():
    assert ib.check_payload({"style": 123})["class"] == "TYPE_INVALID"
    assert ib.check_payload({"style": "a", "lyrics": 12345})["class"] == \
        "TYPE_INVALID"
    assert ib.check_payload({"style": "a", "lyrics": "b",
                             "seed": "not-a-seed"})["class"] == "TYPE_INVALID"
    assert ib.check_payload("not-a-dict")["class"] == "TYPE_INVALID"


def test_unicode_payload():
    r = ib.check_payload({"style": "[Tags]\n流行, 女声\n",
                          "lyrics": "[Lyrics]\n你好世界\n"})
    assert r["ok"] is True


def test_empty_fields():
    r = ib.check_payload({"style": "", "lyrics": ""})
    assert r["ok"] is True  # server has its own instrumental fallback


def test_cli_bounded_exit(tmp_path, capsys):
    p = tmp_path / "payload.json"
    p.write_text(json.dumps(mx.REPEATED_TAGS_PAYLOAD))
    rc = ib.main([str(p), "--receipt", str(tmp_path / "r.json")])
    assert rc == 4
    out = json.loads(capsys.readouterr().out)
    assert out["class"] == "STYLE_DEGENERATE_REPETITION"
    p2 = tmp_path / "ok.json"
    p2.write_text(json.dumps({"style": "[Tags]\npop\n",
                              "lyrics": "[Lyrics]\nA.\n"}))
    assert ib.main([str(p2)]) == 0


def test_matrix_carries_rca_flags():
    """The reliability-matrix runner must expose the RCA-driven cases."""
    import argparse
    ap = argparse.ArgumentParser()
    # mirror the parser surface by checking the source flags exist
    src = (REPO / "scripts" / "rc4_reliability_matrix.py").read_text()
    assert "--repeated-tags-short" in src
    assert "--repeated-tags-default" in src
    assert "BOUNDED_REJECT" in src
    assert "input_budget" in src


def test_repeated_tags_payload_shape():
    """Pin the exact RC4 defect-candidate payload (2/2 >60s timeouts)."""
    p = mx.REPEATED_TAGS_PAYLOAD
    assert p["style"] == "[Tags]\nx\n" * 200
    assert len(json.dumps(p).encode()) < 4096  # ~2.6 KB class
