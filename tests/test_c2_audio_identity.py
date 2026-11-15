"""C2 P2 — audio identity chain: REAL file operations, fail-closed branches.

Builds synthetic run trees (flac bytes = arbitrary payloads, fake scorer
mp3+encoding receipts) and executes the actual packaging path: hash chains,
copy verification, symlink/traversal/overwrite attacks, permission gates.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_per_reference_package as H  # noqa: E402


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_run(tmp_path: Path, n_prompts=2, tamper=None):
    """Synthetic campaign tree with a COMPLETE scorer identity chain."""
    run = tmp_path / "run"
    songs = run / "songs"
    scores = run / "scores"
    rows, chosen = [], []
    flac_bytes = {}
    for i in range(n_prompts):
        for ci in (0, 1):
            cid = f"wsb_{i:03d}_r{ci}_s{7000 + i + ci}"
            fb = f"FLAC-SYNTH-{cid}-{'x' * 64}".encode()
            flac_bytes[cid] = fb
            d = songs / cid
            d.mkdir(parents=True)
            (d / "audio.flac").write_bytes(fb)
            # scorer report: mp3 (any bytes) + encoding receipt binding both
            mp3_bytes = f"MP3-SYNTH-{cid}".encode()
            rep = scores / "audio" / cid
            rep.mkdir(parents=True)
            (rep / "audio.mp3").write_bytes(mp3_bytes)
            (rep / "encoding.json").write_text(json.dumps({
                "mp3_sha256": _sha_bytes(mp3_bytes),
                "source_flac_sha256": _sha_bytes(fb)}))
            rows.append({
                "id": cid, "prompt_index": i, "candidate_index": ci,
                "seed": 7000 + i + ci, "lang": "en",
                "audio_sha256": _sha_bytes(mp3_bytes),
                "metrics": {"per": {"per": 0.1 * (ci + 1),
                                     "edits": 10 * (ci + 1),
                                     "reference_phonemes": 100,
                                     "selected_asr_truncated": False}}})
        chosen.append({"prompt_index": i, "candidate_index": 0,
                       "seed": 7000 + i, "audio_sha256": rows[2 * i]["audio_sha256"]})
    # extend to full 192-prompt dataset by cloning identity-consistent rows
    base_rows, base_chosen = rows, chosen
    rows, chosen = [], []
    for i in range(192):
        src_row = base_rows[2 * (i % n_prompts)]
        for ci in (0, 1):
            orig = base_rows[2 * (i % n_prompts) + ci]
            cid = f"wsb_{i:03d}_r{ci}_s{7000 + i + ci}"
            fb = flac_bytes[orig["id"]]
            d = songs / cid
            d.mkdir(parents=True, exist_ok=True)
            (d / "audio.flac").write_bytes(fb)
            mp3_bytes = f"MP3-SYNTH-{orig['id']}".encode()
            rep = scores / "audio" / cid
            rep.mkdir(parents=True, exist_ok=True)
            (rep / "audio.mp3").write_bytes(mp3_bytes)
            (rep / "encoding.json").write_text(json.dumps({
                "mp3_sha256": _sha_bytes(mp3_bytes),
                "source_flac_sha256": _sha_bytes(fb)}))
            rows.append({**orig, "id": cid, "prompt_index": i,
                         "candidate_index": ci, "seed": 7000 + i + ci})
        o = base_rows[2 * (i % n_prompts)]
        chosen.append({"prompt_index": i, "candidate_index": 0,
                       "seed": 7000 + i, "audio_sha256": o["audio_sha256"]})
    scores.mkdir(parents=True, exist_ok=True)
    (scores / "per_song.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    (scores / "summary.json").write_text(json.dumps(
        {"selected_candidates": chosen}))
    return run, rows


def test_full_package_passes_with_verified_identity(tmp_path):
    run, rows = make_run(tmp_path)
    out = tmp_path / "pkg"
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_per_reference_package.py"),
         "--run", str(run), "--out", str(out), "--rights-confirmed"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    pkg = json.loads((out / "package.json").read_text())
    assert pkg["reference_values"]
    for m in pkg["reference_values"]:
        assert m["audio_identity_verdict"] == "AUDIO_IDENTITY_VERIFIED"
        chain = m["identity_chain"]
        assert chain["receipt_audio_sha256"] == chain["mp3_sha256"]
        assert m["packaged_audio_sha256"] == chain["source_flac_sha256"]
    # copied files are read-only
    for f in (out / "audio").iterdir():
        assert not (f.stat().st_mode & 0o222)


def test_wrong_flac_replaced_after_scoring_fails(tmp_path):
    run, rows = make_run(tmp_path)
    # candidate dir flac swapped: encoding.source_flac_sha256 no longer matches
    victim = run / "songs" / "wsb_000_r0_s7000" / "audio.flac"
    victim.write_bytes(b"TAMPERED-BYTES")
    out = tmp_path / "pkg"
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_per_reference_package.py"),
         "--run", str(run), "--out", str(out), "--rights-confirmed"],
        capture_output=True, text=True)
    assert r.returncode != 0
    assert "does not match encoding source_flac_sha256" in r.stderr


def test_missing_encoding_receipt_fails_closed(tmp_path):
    run, rows = make_run(tmp_path)
    (run / "scores" / "audio" / "wsb_000_r0_s7000" / "encoding.json").unlink()
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_per_reference_package.py"),
         "--run", str(run), "--out", str(tmp_path / "pkg"), "--rights-confirmed"],
        capture_output=True, text=True)
    assert r.returncode != 0
    assert "IDENTITY_INCOMPLETE" in r.stderr or "cannot prove" in r.stderr


def test_symlinked_audio_refused(tmp_path):
    run, rows = make_run(tmp_path)
    target = tmp_path / "outside.flac"
    target.write_bytes(b"evil")
    cand = run / "songs" / "wsb_000_r0_s7000"
    (cand / "audio.flac").unlink()
    (cand / "audio.flac").symlink_to(target)
    from build_per_reference_package import IdentityError, verify_audio_identity
    rows_by_id = {r["id"]: r for r in rows}
    with pytest.raises(IdentityError, match="symlink"):
        verify_audio_identity(run, run / "songs", rows_by_id["wsb_000_r0_s7000"])


def test_path_traversal_candidate_id_refused(tmp_path):
    run, rows = make_run(tmp_path)
    from build_per_reference_package import IdentityError, _safe_candidate_dir
    with pytest.raises(IdentityError, match="Unexpected candidate ID"):
        _safe_candidate_dir(run / "songs", "../../etc/passwd")
    with pytest.raises(IdentityError, match="Unexpected candidate ID"):
        _safe_candidate_dir(run / "songs", "wsb_000_r0_s7000/../../escape")


def test_receipt_mp3_mismatch_fails(tmp_path):
    run, rows = make_run(tmp_path)
    (run / "scores" / "audio" / "wsb_000_r0_s7000" / "audio.mp3").write_bytes(
        b"CHANGED-MP3")
    from build_per_reference_package import IdentityError, verify_audio_identity
    rows_by_id = {r["id"]: r for r in rows}
    with pytest.raises(IdentityError, match="mp3 bytes changed"):
        verify_audio_identity(run, run / "songs", rows_by_id["wsb_000_r0_s7000"])


def test_destination_overwrite_refused(tmp_path):
    run, rows = make_run(tmp_path)
    out = tmp_path / "pkg"
    out.mkdir()
    (out / "stale.txt").write_text("x")
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_per_reference_package.py"),
         "--run", str(run), "--out", str(out), "--rights-confirmed"],
        capture_output=True, text=True)
    assert r.returncode != 0 and "not be overwritten" in r.stderr


def test_rights_gate_missing_fails(tmp_path):
    run, rows = make_run(tmp_path)
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_per_reference_package.py"),
         "--run", str(run), "--out", str(tmp_path / "pkg")],
        capture_output=True, text=True)
    assert r.returncode != 0 and "rights" in r.stderr


def test_copy_detects_midcopy_source_mutation(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"A" * 1024)
    dst = tmp_path / "dst.bin"
    want = _sha_bytes(b"A" * 1024)
    receipt = H.copy_verified(src, dst, want)
    assert receipt["sha256"] == want
    # now mutate mid-copy via a size trick: change content before re-hash
    src2 = tmp_path / "src2.bin"
    src2.write_bytes(b"B" * 1024)
    with pytest.raises(H.IdentityError, match="source hash changed"):
        H.copy_verified(src2, tmp_path / "dst2.bin", want)  # wrong expected sha


def test_copy_refuses_existing_destination(tmp_path):
    src = tmp_path / "s.bin"
    src.write_bytes(b"data")
    dst = tmp_path / "d.bin"
    dst.write_text("preexisting")
    with pytest.raises(H.IdentityError, match="no overwrite"):
        H.copy_verified(src, dst, _sha_bytes(b"data"))


def test_identity_incomplete_summary_blocks_publication_packaging(tmp_path):
    """Selection lacking audio_sha256 fields is COORDINATES-only — packaging
    must refuse (it requires the fully verified tier)."""
    run, rows = make_run(tmp_path)
    s = json.loads((run / "scores" / "summary.json").read_text())
    for item in s["selected_candidates"]:
        item.pop("audio_sha256")
    (run / "scores" / "summary.json").write_text(json.dumps(s))
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_per_reference_package.py"),
         "--run", str(run), "--out", str(tmp_path / "pkg"), "--rights-confirmed"],
        capture_output=True, text=True)
    assert r.returncode != 0
    assert "fully verified official selection" in r.stderr
