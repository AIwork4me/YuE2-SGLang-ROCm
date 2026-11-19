#!/usr/bin/env python3
"""build_per_reference_package.py — portable same-audio cross-backend kit.

C2 P2: FULL AUDIO IDENTITY CHAIN, fail-closed. Ground truth for the chain
(read from the frozen scorer source, wsb_eval.py:290-313):

  candidate dir audio.flac
    --(ffmpeg 192k libmp3lame, receipt encoding.json)--> audio.mp3
  per_song row.audio_sha256  == sha256(audio.mp3)          [scoring input]
  encoding.json.source_flac_sha256 == sha256(audio.flac)   [flac binding]
  encoding.json.mp3_sha256       == sha256(audio.mp3)      [encode binding]

The package exports the FLAC (highest fidelity) and verifies BOTH legs plus
the copy, and records an explicit audio_identity_verdict per sample:

  AUDIO_IDENTITY_VERIFIED — every link holds:
    receipt.audio_sha256 == encoding.mp3_sha256 == sha256(source mp3)
    encoding.source_flac_sha256 == sha256(source flac)
    sha256(copied flac) == sha256(source flac), byte counts equal
  IDENTITITY_INCOMPLETE / rejection — any link missing or mismatched.

Rights: --rights-confirmed is the OPERATOR's assertion of permission; the
script never grants rights. No raw lyrics/ASR text leave the run directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from pathlib import Path

from per_tail_analysis import choose_rows
from sample_classification import EMPTY_CONFIRMED, EMPTY_UNKNOWN, empty_state, labels

ID_RE = re.compile(r"wsb_\d{3}_r[01]_s\d+")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


class IdentityError(ValueError):
    """Fail-closed packaging refusal (never a warning)."""


def _safe_candidate_dir(songs: Path, cid: str) -> Path:
    if not ID_RE.fullmatch(cid):
        raise IdentityError(f"Unexpected candidate ID; refusing filesystem path: {cid!r}")
    d = (songs / cid).resolve()
    if not str(d).startswith(str(songs.resolve()) + os.sep):
        raise IdentityError(f"path escapes songs directory: {cid}")
    if d.is_symlink() or (songs / cid).is_symlink():
        raise IdentityError(f"symlinked candidate dir refused: {cid}")
    return songs / cid


def verify_audio_identity(run_dir: Path, songs: Path, row: dict,
                          encoding_dir_hint: Path | None = None) -> dict:
    """Verify the full chain for one candidate. Raises IdentityError on any
    missing/mismatched link; returns the link receipt on success."""
    cid = row["id"]
    cand = _safe_candidate_dir(songs, cid)
    flac = cand / "audio.flac"
    if not flac.is_file():
        raise IdentityError(f"{cid}: source audio.flac missing")
    if flac.is_symlink():
        raise IdentityError(f"{cid}: audio.flac is a symlink")

    # locate the scorer's mp3 + encoding receipt (report layout: audio/<id>/)
    enc_locations = [encoding_dir_hint] if encoding_dir_hint else [
        run_dir / "scores" / "audio" / cid,
        run_dir / "audio" / cid,
    ]
    encoding = None
    for loc in enc_locations:
        ej = loc / "encoding.json"
        mp3 = loc / "audio.mp3"
        if ej.is_file() and mp3.is_file():
            encoding = (ej, mp3)
            break
    if encoding is None:
        raise IdentityError(
            f"{cid}: scorer MP3/encoding.json receipt missing — cannot prove "
            f"this flac is the scored audio (IDENTITY_INCOMPLETE)")
    ej, mp3 = encoding
    receipt = json.loads(ej.read_text())
    row_sha = row.get("audio_sha256")
    if not isinstance(row_sha, str) or len(row_sha) != 64:
        raise IdentityError(f"{cid}: per_song receipt lacks audio_sha256")

    mp3_now = sha(mp3)
    if receipt.get("mp3_sha256") != row_sha:
        raise IdentityError(f"{cid}: encoding.mp3_sha256 != receipt.audio_sha256")
    if mp3_now != row_sha:
        raise IdentityError(f"{cid}: mp3 bytes changed since scoring")
    flac_now = sha(flac)
    if receipt.get("source_flac_sha256") != flac_now:
        raise IdentityError(f"{cid}: audio.flac does not match encoding "
                            f"source_flac_sha256 (wrong/replaced file?)")
    return {"candidate": cid,
            "receipt_audio_sha256": row_sha,
            "mp3_sha256": mp3_now,
            "source_flac_sha256": flac_now,
            "flac_bytes": flac.stat().st_size}


def pick_stratified(per_song: Path, summary: dict, n_per_bucket=2):
    rows = [json.loads(l) for l in per_song.read_text().splitlines() if l.strip()]
    selected, _, provenance, audit = choose_rows(rows, summary)
    if provenance != "OFFICIAL_SELECTION_AUDIO_IDENTITY_VERIFIED":
        raise ValueError(
            "publication-grade packaging requires the fully verified official "
            f"selection (got {provenance}; missing={audit and audit['missing_fields'][:4]})")

    def bucket(rs, name):
        rs = sorted(rs, key=lambda r: r["metrics"]["per"]["per"])
        out = []
        if rs:
            size = min(n_per_bucket, len(rs))
            for label, ids in (
                ("lowest", range(size)),
                ("median", range(max(0, len(rs) // 2 - size // 2),
                                 min(len(rs), max(0, len(rs) // 2 - size // 2) + size))),
                ("highest", range(len(rs) - size, len(rs)))):
                out += [(name, label, rs[i]) for i in ids]
        return out

    # C2 P1: evidence-based stratification. Empty buckets require DIRECT
    # transcript evidence; PER>=0.999 with unknown transcript is labelled
    # exactly that (never "empty"). Language buckets draw from ALL selected —
    # EMPTY_UNKNOWN (redacted receipts) is the normal public state and does
    # not exclude a sample from language stratification.
    by_empty: dict[str, list] = {EMPTY_CONFIRMED: []}
    for r in selected:
        state, _ = empty_state(r)
        if state == EMPTY_CONFIRMED:
            by_empty[EMPTY_CONFIRMED].append(r)
    per999_unknown = [r for r in selected
                      if "HIGH_PER" not in labels(r)
                      and (empty_state(r)[0]) != EMPTY_CONFIRMED
                      and r["metrics"]["per"]["per"] >= 0.999]
    capped = [r for r in selected if "ASR_CAPPED" in labels(r)]
    high = [r for r in selected
            if "HIGH_PER" in labels(r) and "ASR_CAPPED" not in labels(r)]
    zh = [r for r in selected if r.get("lang") == "zh"
          and "ASR_CAPPED" not in labels(r) and "HIGH_PER" not in labels(r)]
    en = [r for r in selected if r.get("lang") == "en"
          and "ASR_CAPPED" not in labels(r) and "HIGH_PER" not in labels(r)]
    picked = (bucket(by_empty[EMPTY_CONFIRMED], "empty_confirmed")
              + bucket(per999_unknown, "per_ge_0_999_empty_unknown")
              + bucket(capped, "asr_capped")
              + bucket(high, "high_per")
              + bucket(zh, "lang_zh") + bucket(en, "lang_en"))
    seen: set[str] = set()
    strat = []
    for b, rank, r in picked:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        state, evidence = empty_state(r)
        strat.append({"id": r["id"], "bucket": b, "rank": rank,
                      "empty_state": state, "labels": labels(r),
                      "per_this_backend": r["metrics"]["per"]["per"],
                      "lang": r.get("lang"),
                      "prompt_index": r["prompt_index"],
                      "candidate_index": r["candidate_index"],
                      "seed": r["seed"]})
    return strat


def restricted_per_numeric_record(row: dict) -> dict:
    """Never includes target lyrics, ASR transcript or phoneme sequences."""
    m = row["metrics"]["per"]
    return {
        "id": row["id"],
        "prompt_index": row["prompt_index"],
        "candidate_index": row["candidate_index"],
        "seed": row["seed"],
        "audio_sha256": row.get("audio_sha256"),
        "lang": row.get("lang"),
        "metrics": {"per": {
            key: m.get(key)
            for key in ("per", "edits", "reference_phonemes",
                        "selected_asr_truncated", "truncated")
        }},
    }


def copy_verified(src: Path, dst: Path, expected_sha: str) -> dict:
    """Copy with pre/post hash + size + stat-identity checks, committed via a
    RACE-FREE hardlink no-clobber publication (C2.1 P0-B).

    The old `if dst.exists(): raise ... os.replace(tmp, dst)` had a TOCTOU
    window (another process could create dst between check and replace, and
    os.replace overwrites). os.link(2) is kernel-atomic: it fails EEXIST for
    ANY pre-existing destination form (file/symlink/dangling)."""
    if os.path.lexists(dst):
        raise IdentityError(f"destination already exists (no overwrite): {dst.name}")
    st_before = src.stat()
    before = sha(src)
    if before != expected_sha:
        raise IdentityError(f"source hash changed before copy: {src.name}")
    tmp = dst.with_name(dst.name + ".partial-" + uuid.uuid4().hex)
    try:
        with open(src, "rb") as fsrc, open(tmp, "xb") as fdst:
            while True:
                chunk = fsrc.read(1 << 22)
                if not chunk:
                    break
                fdst.write(chunk)
        copied = sha(tmp)
        st_after = src.stat()
        after_src = sha(src)
        if after_src != before:
            raise IdentityError(f"source mutated during copy: {src.name}")
        if copied != before:
            raise IdentityError(f"copy corruption detected: {dst.name}")
        if st_after.st_size != st_before.st_size:
            raise IdentityError(f"source size changed during copy: {src.name}")
        if st_after.st_ino != st_before.st_ino or st_after.st_dev != st_before.st_dev:
            raise IdentityError(f"source file identity changed during copy: {src.name}")
        # atomic, no-clobber publication (fails EEXIST on ANY race loser)
        from atomic_publish import link_no_clobber, PublishError
        try:
            link_no_clobber(tmp, dst)
        except PublishError as exc:
            raise IdentityError(f"destination collision at commit: {exc}") from exc
    finally:
        if os.path.lexists(tmp):
            tmp.unlink()
    return {"sha256": copied, "bytes": dst.stat().st_size,
            "source_stable": True}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True, help="campaign run dir")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--rights-confirmed", action="store_true",
                    help="Operator asserts verified permission for restricted "
                         "sharing of this audio (the script grants nothing)")
    ap.add_argument("--n-per-bucket", type=int, default=2)
    args = ap.parse_args()
    if not args.rights_confirmed:
        ap.error("Audio contains benchmark-derived lyrics; explicit rights "
                 "clearance (--rights-confirmed) is required")
    if args.n_per_bucket <= 0:
        ap.error("--n-per-bucket must be positive")
    import os as _os
    if _os.path.lexists(args.out):
        if args.out.is_symlink():
            ap.error("Destination path is a symlink — refusing")
        if not args.out.is_dir() or any(args.out.iterdir()):
            ap.error("Destination already exists non-empty — existing evidence "
                     "must never be overwritten")
    from atomic_publish import publish_directory_no_clobber, PublishError
    per_song = args.run / "scores" / "per_song.jsonl"
    summary_file = args.run / "scores" / "summary.json"
    if not summary_file.is_file():
        ap.error("Frozen official selection scores/summary.json is required")
    summary = json.loads(summary_file.read_text())
    songs = args.run / "songs"
    strat = pick_stratified(per_song, summary, args.n_per_bucket)

    rows_by_id = {}
    for line in per_song.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            rows_by_id[r["id"]] = r

    # C2.1 P0-A: everything is built in a SIBLING staging directory and
    # published in ONE atomic no-clobber rename. Any failure leaves the final
    # path untouched (never a partial package).
    staging = args.out.with_name(
        args.out.name + ".staging-" + uuid.uuid4().hex)
    # Restricted benchmark-derived bytes must never be exposed via default
    # 0755 staging directories. Mode 0700 survives atomic rename to final.
    staging.mkdir(mode=0o700, parents=True)
    audio_out = staging / "audio"
    audio_out.mkdir(mode=0o700)
    manifest = []
    problems = []
    failure_receipt = {"staging": staging.name, "problems": []}

    def abort(reasons):
        """Fail closed: destroy staging (audio bytes never linger outside the
        run directory), leave a content-free diagnostic receipt, final path
        untouched."""
        import shutil
        failure_receipt["problems"] = reasons[:20]
        try:
            shutil.rmtree(staging)
        except OSError as cleanup_exc:
            # Never silently claim cleanup: leftover benchmark-derived bytes
            # remain restricted (0700) and require explicit manual removal.
            print(
                "::error::restricted staging cleanup FAILED "
                f"({type(cleanup_exc).__name__}); "
                f"manual cleanup required for {staging.name}",
                file=sys.stderr,
            )
        for p in reasons[:20]:
            print("::error::" + p, file=sys.stderr)
        ap.error(f"{len(reasons)} failures — package REFUSED; final path "
                 f"never created (fail-closed, nothing partially exported)")

    for s in strat:
        row = rows_by_id[s["id"]]
        try:
            links = verify_audio_identity(args.run, songs, row)
            cand = _safe_candidate_dir(songs, s["id"])
            dst = audio_out / (s["id"] + ".flac")
            copy_receipt = copy_verified(cand / "audio.flac", dst,
                                         links["source_flac_sha256"])
            if copy_receipt["sha256"] != links["source_flac_sha256"]:
                raise IdentityError(f"{s['id']}: copied hash != source hash")
            manifest.append({**s, "file": dst.name,
                             "packaged_audio_sha256": copy_receipt["sha256"],
                             "flac_bytes": copy_receipt["bytes"],
                             "audio_identity_verdict": "AUDIO_IDENTITY_VERIFIED",
                             "identity_chain": links})
        except IdentityError as exc:
            problems.append(str(exc))
        except OSError as exc:
            # Disk / permission failures must use the SAME private-stage
            # abort path as identity failures; no partial public package.
            problems.append(
                f"candidate {s['id']}: staging I/O failed "
                f"({type(exc).__name__})"
            )
    if problems:
        abort(problems)
    for m in manifest:
        (audio_out / m["file"]).chmod(0o444)  # read-only export

    pkg = {
        "package": "yue2-w7900-per-reference-scoring",
        "schema": "per-reference-package/v2",
        "created_utc": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ",
                                                   __import__("time").gmtime()),
        "purpose": ("Same-audio, different-evaluator experiment (P6.3): score "
                    "this audio with the OFFICIAL vLLM ASR backend on a CUDA "
                    "host and compare per-sample PER vs the ROCm "
                    "qwen_asr/transformers receipts included here."),
        "restriction": ("Audio generated from licensed WildSongBench prompt "
                        "lyrics under the dataset research license; for YuE2 "
                        "authors / evaluation hosts ONLY; no public "
                        "redistribution."),
        "audio_identity_contract": {
            "receipt_audio_sha256": "sha256 of the scorer's audio.mp3 (per_song row)",
            "chain": ["per_song.audio_sha256 == encoding.mp3_sha256 == sha256(mp3)",
                      "encoding.source_flac_sha256 == sha256(source flac)",
                      "sha256(copied flac) == sha256(source flac), bytes equal"],
            "verdict": "AUDIO_IDENTITY_VERIFIED required per sample",
        },
        "evaluator_pins": {
            "dataset_revision": "e361b85a8d7365d3079fa9647641a87ce3c8c5b5",
            "evaluator_bundle_sha256": "bd550b36f1fc43cad3254a9897dd3a078e50c4eb9e8d4f295ac4b5e81d1fc4fd",
            "asr_weights": "Qwen/Qwen3-ASR-1.7B @ 7278e1e70fe206f11671096ffdd38061171dd6e5",
            "official_backend": "vllm==0.14.0 (CUDA)",
            "rocm_backend_used_for_reference_values": (
                "qwen_asr transformers under WSB_ROCM_TORCH_OVERRIDE=1 (patch 0007)"),
        },
        "expected_result_schema": {
            "per_sample": {"id": "str", "per": "float", "edits": "int",
                           "phonemes": "int", "transcript": "str (restricted)"},
            "comparison": ("per-sample PER difference vs reference_values; "
                           "mean/median; bias by duration/lang/capping; "
                           "agreement at selection boundary"),
        },
        "reference_values": manifest,
        "reproducibility_checks": [
            "flac sha256 must match manifest before scoring",
            "reference PER values reproduce from included reference_per.jsonl",
            "official evaluator version banner must show 2026.09.09.2 + vLLM 0.14.0",
            "audio_identity_verdict == AUDIO_IDENTITY_VERIFIED for every sample",
        ],
    }
    # All artifacts are written INTO THE STAGING TREE only (C2.1 P0-A).
    def write_jsonl_staged(name: str, rows: list[dict]):
        p = staging / name
        with open(p, "x", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def write_json_staged(name: str, obj: dict):
        p = staging / name
        with open(p, "x", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

    try:
        write_jsonl_staged("reference_per.jsonl",
                           [restricted_per_numeric_record(rows_by_id[m["id"]])
                            for m in manifest])
        write_jsonl_staged("evaluation_inputs.jsonl",
                           [{"prompt_index": m["prompt_index"],
                             "candidate_index": m["candidate_index"],
                             "seed": m["seed"],
                             "path": f"audio/{m['file']}"}
                            for m in manifest])
        write_json_staged("package.json", pkg)
    except OSError as exc:
        abort([f"staged artifact write failed: {exc}"])

    # Package Completeness Audit: re-verify EVERY staged file against the
    # manifest (sha + bytes + count) before anything is published.
    audit_problems = []
    staged_files = sorted(f.name for f in audio_out.iterdir())
    expected_files = sorted(m["file"] for m in manifest)
    if staged_files != expected_files:
        audit_problems.append(
            f"staged audio set != manifest ({len(staged_files)} vs "
            f"{len(expected_files)} files)")
    for m in manifest:
        f = audio_out / m["file"]
        if not f.is_file():
            audit_problems.append(f"missing staged audio: {m['file']}")
            continue
        if sha(f) != m["packaged_audio_sha256"] or f.stat().st_size != m["flac_bytes"]:
            audit_problems.append(f"staged audio drifted: {m['file']}")
    if audit_problems:
        abort(audit_problems)
    try:
        write_json_staged(".package_audit.json", {
            "audited_at_utc": __import__("time").strftime(
                "%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
            "files_audited": len(manifest),
            "result": "COMPLETE",
        })
    except OSError as exc:
        abort([f"staged audit write failed ({type(exc).__name__})"])

    # SINGLE atomic no-clobber publication: staging -> final. Failure modes:
    #   concurrent winner -> EEXIST -> we abort (our staging is discarded,
    #   the winner's package is untouched)
    #   fs lacking RENAME_NOREPLACE -> PublishError -> abort (fail closed)
    #   crash before/during rename -> final never existed or is fully the
    #   winner's; an orphaned .staging-<uuid> sibling may remain (clearly
    #   named, never mistaken for the package)
    try:
        publish_directory_no_clobber(staging, args.out)
    except PublishError as exc:
        abort([f"atomic publication refused: {exc}"])
    print(f"package at {args.out}: {len(manifest)} samples, "
          f"all AUDIO_IDENTITY_VERIFIED, published atomically (staging "
          f"{staging.name} no longer exists)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
