"""Regression tests for the CUDA handoff bundle verifier (RC3 security fix).

Positive control: a self-contained synthetic mini-bundle verifies OK.
Negative controls (each must fail CLOSED with a precise message):
  1. a file replaced by a symlink pointing OUTSIDE the bundle with a matching
     hash — the defect this suite pins: the pre-RC3 verifier accepted it
     because sha256(is_symlink->outside content) matched the manifest;
  2. a dangling symlink;
  3. a crafted manifest id carrying a path-traversal payload;
  4. an absolute / traversing evaluation_inputs path;
  5. a corrupt hash (classic corruption);
  6. a truncated file (size mismatch);
  7. a missing required artifact from the manifest entry;
  8. a duplicate manifest id;
  9. manifest id whose index fields disagree with the id string.

The verifier hard-codes the 384-candidate standard-mode contract; the tests
exercise it through a 384-row synthetic manifest with tiny fixture files so
the REAL code path (including the count gates) runs unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERIFIER = (REPO / "reports/joint_blog_rc/rc2/RC2_03_AUTHOR_CUDA_HANDOFF"
            / "verify_transfer_bundle.py")

REQUIRED = ["audio.flac", "prefix.npy", "semantic.npy", "latent.npy",
            "request.json", "config.json", "result.json"]


def _candidate_dir(bundle: Path, idx: int, j: int) -> Path:
    return bundle / "songs" / f"wsb_{idx:03d}_r{j}_s{831001 + idx if j == 0 else 831019 + idx}"


def _fill(cand: Path, *, flac: bytes = b"f") -> dict:
    cand.mkdir(parents=True, exist_ok=True)
    files = {}
    payload = {"audio.flac": flac * 64, "prefix.npy": b"p", "semantic.npy": b"s",
               "latent.npy": b"l", "request.json": b"{}", "config.json": b"{}",
               "result.json": b"{}"}
    for name, data in payload.items():
        (cand / name).write_bytes(data)
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(),
                       "bytes": len(data)}
    return files


def _build(bundle: Path, *, count: int = 384) -> dict:
    shutil.rmtree(bundle, ignore_errors=True)
    (bundle / "songs").mkdir(parents=True)
    entries, rows = [], []
    for i in range(count // 2):
        for j in (0, 1):
            seed = 831001 + i if j == 0 else 831019 + i
            cid = f"wsb_{i:03d}_r{j}_s{seed}"
            files = _fill(bundle / "songs" / cid)
            entries.append({"id": cid, "prompt_index": i,
                            "candidate_index": j, "seed": seed, "files": files})
            rows.append({"prompt_index": i, "candidate_index": j, "seed": seed,
                         "path": f"songs/{cid}"})
    (bundle / "evaluation_inputs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    return {"schema": "rc2-cuda-transfer-bundle/v2", "count": len(entries),
            "files": entries}


def _verify(bundle: Path, manifest_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(VERIFIER),
                           "--bundle", str(bundle),
                           "--manifest", str(manifest_path)],
                          capture_output=True, text=True)


def test_positive_control_minimal_bundle_verifies(tmp_path: Path):
    bundle = tmp_path / "b"
    m = _build(bundle)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "bundle OK: 384 candidates" in r.stdout
    assert "no symlinks" in r.stdout


def test_symlink_escape_rejected(tmp_path: Path):
    """THE RC3 defect: out-of-bundle symlink with matching hash was accepted."""
    bundle = tmp_path / "b"
    m = _build(bundle)
    # keep an untouched copy of the real file OUTSIDE the bundle
    outside = tmp_path / "outside.flac"
    cand = _candidate_dir(bundle, 0, 0)
    outside.write_bytes((cand / "audio.flac").read_bytes())
    (cand / "audio.flac").unlink()
    (cand / "audio.flac").symlink_to(outside.resolve())
    assert (cand / "audio.flac").is_symlink()
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 1
    assert "symlink rejected" in r.stdout, r.stdout


def test_dangling_symlink_rejected(tmp_path: Path):
    bundle = tmp_path / "b"
    m = _build(bundle)
    cand = _candidate_dir(bundle, 1, 0)
    (cand / "result.json").unlink()
    (cand / "result.json").symlink_to(tmp_path / "gone.json")
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 1
    assert "symlink" in r.stdout or "missing" in r.stdout


def test_path_traversal_manifest_id_rejected(tmp_path: Path):
    bundle = tmp_path / "b"
    m = _build(bundle)
    m["files"][0] = {**m["files"][0],
                     "id": "../../etc/passwd-wsb_000_r0_s831001"}
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 1
    assert "naming contract" in r.stdout


def test_absolute_inputs_path_rejected(tmp_path: Path):
    bundle = tmp_path / "b"
    m = _build(bundle)
    rows = [json.loads(l) for l in
            (bundle / "evaluation_inputs.jsonl").read_text().splitlines()]
    rows[5]["path"] = "/etc/passwd"
    (bundle / "evaluation_inputs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 1
    assert "not 'songs/<manifest id>'" in r.stdout


def test_traversing_inputs_path_rejected(tmp_path: Path):
    bundle = tmp_path / "b"
    m = _build(bundle)
    rows = [json.loads(l) for l in
            (bundle / "evaluation_inputs.jsonl").read_text().splitlines()]
    rows[7]["path"] = f"songs/../../{rows[7]['path']}"
    (bundle / "evaluation_inputs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 1
    assert "not 'songs/<manifest id>'" in r.stdout


def test_corrupt_hash_rejected(tmp_path: Path):
    bundle = tmp_path / "b"
    m = _build(bundle)
    p = _candidate_dir(bundle, 3, 1) / "config.json"
    p.write_bytes(b"~}")  # same 2-byte size, different content -> hash mismatch
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 1
    assert "sha256 mismatch" in r.stdout


def test_truncated_transfer_rejected(tmp_path: Path):
    bundle = tmp_path / "b"
    m = _build(bundle)
    p = _candidate_dir(bundle, 4, 0) / "audio.flac"
    data = p.read_bytes()
    p.write_bytes(data[:len(data) // 2])  # shorter than manifest bytes
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 1
    assert "size" in r.stdout and "!=" in r.stdout


def test_manifest_missing_required_rejected(tmp_path: Path):
    bundle = tmp_path / "b"
    m = _build(bundle)
    del m["files"][2]["files"]["latent.npy"]
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 1
    assert "manifest lacks required" in r.stdout


def test_duplicate_manifest_id_rejected(tmp_path: Path):
    bundle = tmp_path / "b"
    m = _build(bundle)
    m["files"][1] = {**m["files"][0]}
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 1
    assert "duplicate manifest id" in r.stdout


def test_manifest_index_disagreement_rejected(tmp_path: Path):
    bundle = tmp_path / "b"
    m = _build(bundle)
    m["files"][0]["prompt_index"] = 191  # id says prompt 0
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    r = _verify(bundle, mp)
    assert r.returncode == 1
    assert "index fields disagree" in r.stdout
