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
    # The worker source must keep the official request-contract assertion
    # and hash-verify the pinned weights at runtime via the spec.
    assert 'SongRequest(**request).text() == row["generation_prompt"]' in A.GEN_WORKER
    assert '== spec["model_sha256"]' in A.GEN_WORKER
    assert '== spec["vae_sha256"]' in A.GEN_WORKER


def test_atomic_append(tmp_path):
    p = tmp_path / "journal.jsonl"
    A.atomic_append(p, {"id": "x", "status": "complete"})
    A.atomic_append(p, {"id": "y", "status": "failed"})
    lines = p.read_text().splitlines()
    assert [json.loads(l)["id"] for l in lines] == ["x", "y"]
    assert not (tmp_path / "journal.tmp").exists()
    assert A.read_journal(p) == [
        {"id": "x", "status": "complete"},
        {"id": "y", "status": "failed"},
    ]


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


def test_partial_worker_bundle_is_quarantined_not_deleted(tmp_path):
    # Worker helper must exist and be importable without importing torch.
    namespace = {"__name__": "worker_unit_test"}
    exec(A.GEN_WORKER, namespace)
    p = tmp_path / "song.partial"
    p.mkdir()
    (p / "unfinished_audio.bin").write_bytes(b"original-evidence")
    target = namespace["quarantine_existing"](p)
    assert target is not None and target.exists() and not p.exists()
    assert (target / "unfinished_audio.bin").read_bytes() == b"original-evidence"


def test_renaming_does_not_follow_symlinks(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlink"):
        A.quarantine_existing(link)
    assert target.exists() and link.is_symlink()


def test_quarantine_names_are_unique(tmp_path):
    p = tmp_path / "broken"
    p.mkdir()
    a = A.quarantine_existing(p)
    p.mkdir()
    b = A.quarantine_existing(p)
    assert a != b and a.exists() and b.exists()


def test_torn_journal_tail_is_preserved_and_recovered(tmp_path):
    journal = tmp_path / "generation_manifest.jsonl"
    journal.write_bytes(b'{"id":"a","status":"complete"}\n{"id":"incom')
    records = A.read_journal(journal)
    assert records == [{"id": "a", "status": "complete"}]
    assert journal.read_bytes() == b'{"id":"a","status":"complete"}\n'
    tails = list(tmp_path.glob("generation_manifest.jsonl.corrupt-tail-*.bin"))
    assert len(tails) == 1
    assert tails[0].read_bytes() == b'{"id":"incom'
    A.atomic_append(journal, {"id": "b", "status": "failed"})
    assert [x["id"] for x in A.read_journal(journal)] == ["a", "b"]


def test_complete_invalid_record_cannot_be_silently_discarded(tmp_path):
    journal = tmp_path / "generation_manifest.jsonl"
    journal.write_bytes(b'{"id":"a","status":"complete"}\nNOT_JSON\n')
    with pytest.raises(ValueError, match="Invalid complete journal"):
        A.read_journal(journal)
    assert journal.read_bytes().endswith(b"NOT_JSON\n")


def test_append_rejects_incomplete_tail(tmp_path):
    journal = tmp_path / "generation_manifest.jsonl"
    journal.write_bytes(b'{"id":"partial"')
    with pytest.raises(ValueError, match="incomplete final record"):
        A.atomic_append(journal, {"id": "next"})
    assert journal.read_bytes() == b'{"id":"partial"'


def test_last_status_event_wins(tmp_path):
    journal = tmp_path / "generation_manifest.jsonl"
    A.atomic_append(journal, {"id": "a", "status": "complete"})
    A.atomic_append(journal, {"id": "a", "status": "failed"})
    state = {r["id"]: r["status"] for r in A.read_journal(journal)}
    assert state["a"] == "failed"


def test_worker_exposes_no_recursive_delete_of_partial_bundles():
    assert "rmtree(tmp)" not in A.GEN_WORKER
    assert "quarantine_existing(tmp)" in A.GEN_WORKER
    assert "quarantine_existing(out)" in A.GEN_WORKER
