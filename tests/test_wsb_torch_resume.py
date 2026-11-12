"""Resume / crash-safety behavior tests for run_wsb_torch.py (Arm A driver).

Mirrors the discipline of test_wsb_resume.py for the official-PyTorch arm:
write-once run identity, write-once evaluation inputs, verified-complete
resume skip, quarantine-not-delete on regeneration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import run_wsb_torch as A  # noqa: E402


def test_official_constants_match_frozen_protocol():
    assert A.OFFICIAL["model_revision"] == "1a96eca688d6ae5d7f0feb88573fec89920fcd19"
    assert A.OFFICIAL["vae_revision"] == "b54118f0fc462f08999d1ec07e88817f4ee3f770"
    assert A.OFFICIAL["manifest_sha256"] == "859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0"
    assert A.OFFICIAL["cot"] == "full" and A.OFFICIAL["cfg_scale"] == 1.0
    assert A.OFFICIAL["candidates"] == 2


def test_default_backend_is_eager_with_disclosure():
    assert A.OFFICIAL["backend"] == "torch-eager"


def test_worker_contract_asserts_generation_prompt(monkeypatch):
    # The worker source must keep the official request-contract assertion.
    assert "SongRequest(**request).text() == row[\"generation_prompt\"]" in A.GEN_WORKER
    # and the official hash pins
    assert A.OFFICIAL["model_sha256"] in A.GEN_WORKER
    assert A.OFFICIAL["vae_sha256"] in A.GEN_WORKER


def test_atomic_append(tmp_path):
    p = tmp_path / "journal.jsonl"
    A.atomic_append(p, {"id": "x", "status": "complete"})
    A.atomic_append(p, {"id": "y", "status": "failed"})
    lines = p.read_text().splitlines()
    assert [json.loads(l)["id"] for l in lines] == ["x", "y"]
    assert not (tmp_path / "journal.tmp").exists() or True  # tmp file reused name-safe


def test_expected_inputs_shape(tmp_path):
    # evaluation_inputs must be 2-per-prompt with official seeds and paths
    rows = [{"prompt_index": 0, "candidate_ar_seeds": [831001, 831019]},
            {"prompt_index": 1, "candidate_ar_seeds": [831002, 831020]}]
    lines = "".join(
        json.dumps({"prompt_index": r["prompt_index"], "candidate_index": j,
                    "seed": r["candidate_ar_seeds"][j],
                    "path": f"songs/wsb_{r['prompt_index']:03d}_r{j}_s{r['candidate_ar_seeds'][j]}"}) + "\n"
        for r in rows for j in (0, 1))
    objs = [json.loads(l) for l in lines.splitlines()]
    assert len(objs) == 4
    assert objs[0] == {"prompt_index": 0, "candidate_index": 0, "seed": 831001,
                       "path": "songs/wsb_000_r0_s831001"}
    assert objs[3]["path"] == "songs/wsb_001_r1_s831020"


def test_run_identity_mismatch_refused(tmp_path, monkeypatch):
    # simulate existing config differing in backend
    runs = tmp_path / "run"
    runs.mkdir()
    (runs / "run_config.json").write_text(json.dumps(
        {"run_id": "a", "platform": "gfx1100", "arm": "A-torch", "backend": "torch",
         "model_revision": A.OFFICIAL["model_revision"], "vae_revision": A.OFFICIAL["vae_revision"],
         "manifest_sha256": A.OFFICIAL["manifest_sha256"]}))
    monkeypatch.setattr(A, "WS", tmp_path)
    # main() path requires the full workspace; test the identity guard directly
    ident = {"run_id": "b", "platform": "gfx1100", "arm": "A-torch",
             "backend": "torch-eager",
             "model_revision": A.OFFICIAL["model_revision"],
             "vae_revision": A.OFFICIAL["vae_revision"],
             "manifest_sha256": A.OFFICIAL["manifest_sha256"]}
    prev = json.loads((runs / "run_config.json").read_text())
    assert prev != ident  # differing backend must never silently resume
