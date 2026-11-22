"""Regression test for the schema-portable truncation counter (RC3 fix).

The auditor's truncated_but_complete previously used bare truthiness on the
manifest row's `truncated` field. The Arm A torch driver records a per-stage
dict {"abc": bool, "semantic": bool} — a non-empty dict is truthy even when
every stage is False, so the Arm A audit reported truncated_but_complete=384
when the true count was ~0. The Arm B SGLang driver records a plain bool and
was counted correctly.

Pinned semantics (is_truncated):
  * bool True -> truncated
  * bool False / None / absent -> not truncated
  * dict with any truthy stage -> truncated
  * dict with all-falsy stages -> not truncated
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from verify_wsb_artifacts import is_truncated  # noqa: E402


def test_bool_schema():
    assert is_truncated(True) is True
    assert is_truncated(False) is False


def test_missing_schema():
    assert is_truncated(None) is False


def test_dict_schema_all_false_is_not_truncated():
    # the exact Arm A shape that previously inflated the count to 384
    assert is_truncated({"abc": False, "semantic": False}) is False


def test_dict_schema_any_stage_true_is_truncated():
    assert is_truncated({"abc": False, "semantic": True}) is True
    assert is_truncated({"abc": True, "semantic": False}) is True
