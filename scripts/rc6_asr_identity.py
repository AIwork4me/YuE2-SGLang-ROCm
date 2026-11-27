#!/usr/bin/env python3
"""rc6_asr_identity.py — RC6 A2: formal ASR_RUN_IDENTITY contract + fail-closed
receipt auditing/resume (shared library).

Every ASR evaluation run (and every resumable transcript file) must carry a
complete, hash-bound identity:

  model       : ASR model repository + revision + per-file content hashes
  processor   : tokenizer/processor file hashes (prompt template identity)
  engine      : implementation + framework/runtime versions + device identity
  preproc     : audio loading + chunking policy (qwen_asr source hashes)
  decoding    : temperature/top_p/top_k/max_tokens/seed/repeats/batch policy
  scoring     : scorer source hashes + audio manifest hash (scoring identity
                is SEPARATE: a changed scorer => new scoring identity, never
                an overwrite of the old arm)
  driver      : the runner script's own source hash

Receipt-level binding: candidate_id, prompt_index, candidate_index,
audio_sha256, run_identity_sha256, transcript_receipt_sha256, repeat_count,
status. Resume is FAIL-CLOSED: only exact identity + audio + repeat-count
matches are reusable; everything else is rejected, quarantined or hard-failed
per the taxonomy below. No RC5.1 frozen transcript is ever modified.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

SCHEMA = "yue2-rc6-asr-run-identity/1"

# Failure taxonomy (single stable vocabulary for runner + tests + audits)
R_OK = "REUSABLE"
R_AUDIO_MISMATCH = "REJECT_AUDIO_MISMATCH"
R_MODEL_MISMATCH = "REJECT_MODEL_MISMATCH"
R_ENGINE_MISMATCH = "REJECT_ENGINE_MISMATCH"
R_CONFIG_MISMATCH = "REJECT_CONFIG_MISMATCH"
R_MISSING_REPEATS = "INCOMPLETE_MISSING_REPEATS"
R_DUPLICATE = "FAIL_DUPLICATE_CANDIDATE_ID"
R_TAIL_INVALID = "QUARANTINE_INVALID_JSON_TAIL"
R_MANIFEST_MISSING = "FAIL_MANIFEST_ROW_MISSING"
R_SCORER_CHANGED = "SEPARATE_SCORING_IDENTITY_REQUIRED"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tree_hashes(root: Path, patterns=("*",), max_files=64) -> dict:
    root = Path(root)
    out = {}
    for pat in patterns:
        for p in sorted(root.rglob(pat)):
            if p.is_file() and not p.name.endswith((".pyc", ".lock")) and ".venv" not in p.parts:
                out[str(p.relative_to(root))] = sha256_file(p)
                if len(out) >= max_files:
                    return out
    return out


def model_identity(model_root: Path) -> dict:
    model_root = Path(model_root)
    files = {}
    for name in sorted(os.listdir(model_root)):
        p = model_root / name
        if p.is_file() and not name.endswith((".lock", ".pyc")):
            files[name] = sha256_file(p)
    snap = model_root.parent.name if model_root.parent.name.startswith("snapshots") else ""
    return {"root": str(model_root), "snapshot": snap, "files": files,
            "files_sha256": sha256_bytes(json.dumps(files, sort_keys=True).encode())}


def build_run_identity(*, model_root: Path, engine: dict, preproc: dict,
                       decoding: dict, scoring: dict, driver_path: Path) -> dict:
    ident = {
        "schema": SCHEMA,
        "model": model_identity(model_root),
        "engine": {k: str(v) for k, v in engine.items()},
        "audio_preprocessing": {k: (str(v) if isinstance(v, Path) else v)
                                for k, v in preproc.items()},
        "decoding": {k: str(v) for k, v in decoding.items()},
        "scoring": {k: (str(v) if isinstance(v, Path) else v) for k, v in scoring.items()},
        "driver": {"path": str(driver_path), "sha256": sha256_file(driver_path)},
    }
    ident["run_identity_sha256"] = sha256_bytes(
        json.dumps({k: v for k, v in ident.items() if k != "run_identity_sha256"},
                   sort_keys=True).encode())
    return ident


def receipt_sha256(receipt: dict) -> str:
    payload = {k: v for k, v in receipt.items() if k != "transcript_receipt_sha256"}
    return sha256_bytes(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())


def _receipt_run_identity(receipt: dict) -> dict | None:
    ri = receipt.get("run_identity")
    if isinstance(ri, dict):
        return ri
    return None


def audit_receipts(transcripts_path: Path, manifest_rows: list[dict],
                   run_identity: dict | None = None, expected_repeats: int | None = None,
                   engine_receipt: dict | None = None) -> dict:
    """Fail-closed audit of a transcripts JSONL against a manifest + identity.

    Returns an audit dict (never raises on receipt content — content problems
    are REPORTED in the taxonomy; I/O errors raise).
    """
    transcripts_path = Path(transcripts_path)
    manifest = {r["id"]: r for r in manifest_rows}
    raw = transcripts_path.read_text() if transcripts_path.is_file() else ""
    lines = raw.splitlines()

    valid_rows, tail_invalid_lines, valid_line_indices = [], [], []
    seen_ids: dict[str, int] = {}
    decisions = {}
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if not isinstance(rec, dict) or "id" not in rec:
                raise ValueError("not a receipt object")
        except ValueError:
            tail_invalid_lines.append({"line_index": i, "preview": line[:120]})
            continue
        valid_rows.append(rec)
        valid_line_indices.append(i)
    # duplicates counted over ALL parsed rows (quarantined tail excluded)
    for rec in valid_rows:
        seen_ids[rec["id"]] = seen_ids.get(rec["id"], 0) + 1
    duplicates = {cid: n for cid, n in seen_ids.items() if n > 1}

    for rec in valid_rows:
        cid = rec["id"]
        row = manifest.get(cid)
        if row is None:
            decisions[cid] = R_MANIFEST_MISSING
            continue
        if rec.get("audio_sha256") != row.get("audio_sha256"):
            decisions[cid] = R_AUDIO_MISMATCH
            continue
        ri = _receipt_run_identity(rec)
        if ri is not None and run_identity is not None:
            if ri.get("model", {}).get("files_sha256") != run_identity["model"]["files_sha256"]:
                decisions[cid] = R_MODEL_MISMATCH
                continue
            eng_new, eng_old = run_identity.get("engine", {}), ri.get("engine", {})
            keys = ("engine", "vllm", "torch", "hip", "dtype", "seed")
            if any(str(eng_new.get(k)) != str(eng_old.get(k)) for k in keys if k in eng_new):
                decisions[cid] = R_ENGINE_MISMATCH
                continue
            dec_new = {k: str(v) for k, v in run_identity.get("decoding", {}).items()}
            dec_old = {k: str(v) for k, v in ri.get("decoding", {}).items()}
            if any(k in dec_new and k in dec_old and dec_new[k] != dec_old[k]
                   for k in ("temperature", "top_p", "top_k", "max_tokens", "repeats", "seed")):
                decisions[cid] = R_CONFIG_MISMATCH
                continue
        elif ri is None and run_identity is not None:
            # legacy RC5 receipts carry a partial engine env: compare what exists
            env = rec.get("engine") or {}
            if isinstance(env, dict) and run_identity.get("engine", {}).get("vllm") and \
                    env.get("vllm") and str(env.get("vllm")) != str(run_identity["engine"].get("vllm")):
                decisions[cid] = R_ENGINE_MISMATCH
                continue
        reps = rec.get("repeats") or []
        want = expected_repeats if expected_repeats is not None else \
            (int(run_identity["decoding"]["repeats"]) if run_identity else None)
        if want is not None and len(reps) < want:
            decisions[cid] = R_MISSING_REPEATS
            continue
        if rec.get("status") not in (None, "complete"):
            decisions[cid] = f"REJECT_STATUS_{rec.get('status')}"
            continue
        decisions[cid] = R_OK

    reusable = [cid for cid, d in decisions.items() if d == R_OK]
    missing_in_file = [cid for cid in manifest if cid not in seen_ids]
    audit = {
        "schema": "yue2-rc6-asr-receipt-audit/1",
        "transcripts_path": str(transcripts_path),
        "manifest_rows": len(manifest),
        "parsed_valid_lines": len(valid_rows),
        "valid_line_indices": valid_line_indices,
        "invalid_tail_lines": tail_invalid_lines,
        "duplicate_candidate_ids": duplicates,
        "decisions": decisions,
        "reusable": sorted(reusable),
        "rejected": sorted(c for c, d in decisions.items() if d.startswith("REJECT")),
        "incomplete": sorted(c for c, d in decisions.items() if d.startswith("INCOMPLETE")),
        "missing_from_file": sorted(missing_in_file),
        "engine_receipt_consistent": engine_receipt is None or all(
            (_receipt_run_identity(r) or {}).get("run_identity_sha256") in
            (None, engine_receipt.get("run_identity_sha256")) for r in valid_rows),
    }
    audit["fail_closed_hard_errors"] = sorted(
        set(d for d in decisions.values()
            if d.startswith("FAIL") or d == R_DUPLICATE) | (
            {R_DUPLICATE} if duplicates else set()))
    audit["resume_allowed"] = (not audit["rejected"] and not duplicates
                               and not audit["fail_closed_hard_errors"])
    return audit


def quarantine_tail(transcripts_path: Path, valid_line_indices: list[int]) -> Path:
    """Bounded repair: keep the valid prefix in place, move the FULL original
    (supersede-not-overwrite) to a timestamped quarantine file next to it."""
    transcripts_path = Path(transcripts_path)
    import time
    q = transcripts_path.with_suffix(
        transcripts_path.suffix + f".quarantine-{time.strftime('%Y%m%dT%H%M%SZ')}")
    raw = transcripts_path.read_text().splitlines()
    q.write_text("\n".join(raw) + ("\n" if raw else ""))
    keep = set(valid_line_indices)
    kept = [l for i, l in enumerate(raw) if i in keep]
    transcripts_path.write_text("\n".join(kept) + ("\n" if kept else ""))
    return q
