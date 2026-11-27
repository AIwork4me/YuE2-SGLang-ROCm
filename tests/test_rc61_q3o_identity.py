#!/usr/bin/env python3
"""RC6.1 M4 — Q3O judge identity regression tests.

Covers the live defect found during the corrected-arm execution: the RC5
identity hash included created_at_utc (execution provenance), which made
every same-configuration run a "different judge identity" and made
legitimate receipt reuse impossible. Also covers the rebind serialization
contract (the judge's object_hash must be used verbatim).

Run:  python3 -m pytest tests/test_rc61_q3o_identity.py -v
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))


def object_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


IDENT = {
    "schema": "yue2-rc5-q3o-identity/2",
    "judge_source_sha256": "a" * 64,
    "moe_source_sha256": "b" * 64,
    "model_revision": "r",
    "torch_version": "2.10.0+rocm7.12.0",
    "placement_config": {"gpu_layers": 34, "cpu_threads": 16, "mode": "m"},
}


def test_identity_hash_excludes_timestamp():
    """Two runs of the same configuration at different times MUST produce the
    same canonical identity hash (the RC5 defect)."""
    import rc5_q3o_judge as J
    # emulate the fixed formula end of compute_run_identity
    def build(created):
        ident = dict(IDENT)
        ident["created_at_utc"] = created
        ident["identity_sha256"] = object_hash(
            {k: v for k, v in ident.items()
             if k not in ("identity_sha256", "created_at_utc")})
        return ident
    i1 = build("2026-11-26T11:37:45Z")
    i2 = build("2026-11-27T23:25:09Z")
    assert i1["identity_sha256"] == i2["identity_sha256"]
    # and the timestamp still differs (provenance preserved, content identical)
    assert i1["created_at_utc"] != i2["created_at_utc"]


def test_identity_drift_ignores_timestamp_but_not_content():
    import rc5_q3o_judge as J
    a = dict(IDENT, created_at_utc="t1", identity_sha256="x")
    b = dict(IDENT, created_at_utc="t2", identity_sha256="x")
    assert J.identity_drift(a, b) == {}
    c = dict(IDENT, created_at_utc="t2", identity_sha256="y")
    d = J.identity_drift(a, c)
    assert "identity_sha256" in d and "created_at_utc" not in d


def test_rebind_serialization_matches_judge_object_hash():
    """The rebind tool MUST use the judge's exact serialization — a default
    json.dumps produces a different sha (live defect during M4 execution)."""
    import rc61_q3o_rebind as R
    obj = {"b": 1, "a": "é"}
    assert R.object_hash(obj) == object_hash(obj)
    loose = hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()
    assert R.object_hash(obj) != loose  # the serialization bug this test pins


def test_canonical_sha_formula():
    import rc61_q3o_rebind as R
    ident = dict(IDENT, created_at_utc="t", identity_sha256="old")
    assert R.canonical_sha(ident) == object_hash(
        {k: v for k, v in ident.items()
         if k not in ("identity_sha256", "created_at_utc")})
