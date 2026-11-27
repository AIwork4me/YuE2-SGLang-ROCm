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

# RC6.1 M2 additions (fail-closed strictness)
R_RECEIPT_HASH = "FAIL_RECEIPT_HASH_MISMATCH"
R_IDENTITY_MISMATCH = "REJECT_IDENTITY_MISMATCH"
R_EXTRA_REPEATS = "REJECT_EXTRA_REPEATS"
R_MIDFILE_CORRUPTION = "FAIL_MIDFILE_CORRUPTION"
R_MANIFEST_DUPLICATES = "FAIL_MANIFEST_DUPLICATE_IDS"
R_HISTORICAL_PARTIAL = "HISTORICAL_RECEIPT_VALID_IDENTITY_PARTIAL"


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


def _identity_content_sha(ident: dict) -> str:
    """Canonical sha over an identity's CONTENT (run_identity_sha256 field
    itself excluded) — strict full-identity comparison basis."""
    payload = {k: v for k, v in ident.items() if k != "run_identity_sha256"}
    return sha256_bytes(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())


def audit_receipts(transcripts_path: Path, manifest_rows: list[dict],
                    run_identity: dict | None = None, expected_repeats: int | None = None,
                    engine_receipt: dict | None = None) -> dict:
    """Fail-closed audit of a transcripts JSONL against a manifest + identity.

    RC6.1 M2 strictness (on top of the RC6 field-level checks):
      * every receipt's transcript_receipt_sha256 is RECOMPUTED — a mutated
        body with a stale hash is FAIL_RECEIPT_HASH_MISMATCH (tamper);
      * the FULL identity is compared (embedded run_identity_sha256, or the
        canonical content hash when the embedded sha is absent) — changes
        outside the historical field subset (preproc/scoring/driver/...) are
        no longer invisible;
      * receipts WITHOUT run_identity (legacy) can never be strict-reusable
        (HISTORICAL_RECEIPT_VALID_IDENTITY_PARTIAL — analysis only);
      * repeat count must be EXACTLY the expected count (extras rejected);
      * malformed JSONL lines with valid lines AFTER them are MID-FILE
        corruption (FAIL_CLOSED, not a repairable tail);
      * duplicate manifest ids are FAIL_MANIFEST_DUPLICATE_IDS.

    Returns an audit dict (never raises on receipt content — content problems
    are REPORTED in the taxonomy; I/O errors raise).
    """
    transcripts_path = Path(transcripts_path)
    manifest_ids = [r.get("id") for r in manifest_rows]
    manifest_dupes = sorted({i for i in manifest_ids if manifest_ids.count(i) > 1})
    manifest = {r["id"]: r for r in manifest_rows}
    raw = transcripts_path.read_text() if transcripts_path.is_file() else ""
    lines = raw.splitlines()

    valid_rows, tail_invalid_lines, valid_line_indices = [], [], []
    midfile_invalid_lines = []
    malformed_indices = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if not isinstance(rec, dict) or "id" not in rec:
                raise ValueError("not a receipt object")
        except ValueError:
            malformed_indices.append(i)
            continue
        valid_rows.append(rec)
        valid_line_indices.append(i)
    last_valid = valid_line_indices[-1] if valid_line_indices else -1
    for i in malformed_indices:
        if i > last_valid:
            tail_invalid_lines.append({"line_index": i, "preview": lines[i][:120]})
        else:
            midfile_invalid_lines.append({"line_index": i, "preview": lines[i][:120]})
    # duplicates counted over ALL parsed rows (quarantined tail excluded)
    seen_ids: dict[str, int] = {}
    for rec in valid_rows:
        seen_ids[rec["id"]] = seen_ids.get(rec["id"], 0) + 1
    duplicates = {cid: n for cid, n in seen_ids.items() if n > 1}

    decisions = {}
    for rec in valid_rows:
        cid = rec["id"]
        # 1) receipt integrity: recompute the content hash first — a tampered
        #    body with a stale hash must never reach the reuse logic
        declared_hash = rec.get("transcript_receipt_sha256")
        if declared_hash is not None:
            actual_hash = receipt_sha256(rec)
            if actual_hash != declared_hash:
                decisions[cid] = R_RECEIPT_HASH
                continue
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
            # strict full-identity binding (M2: no partial-field acceptance)
            expected_sha = run_identity.get("run_identity_sha256")
            embedded_sha = ri.get("run_identity_sha256")
            if expected_sha is not None and embedded_sha is not None:
                if embedded_sha != expected_sha:
                    decisions[cid] = R_IDENTITY_MISMATCH
                    continue
            elif _identity_content_sha(ri) != _identity_content_sha(run_identity):
                decisions[cid] = R_IDENTITY_MISMATCH
                continue
        elif ri is None and run_identity is not None:
            # legacy RC5 receipts carry a partial engine env: compare what exists
            env = rec.get("engine") or {}
            if isinstance(env, dict) and run_identity.get("engine", {}).get("vllm") and \
                    env.get("vllm") and str(env.get("vllm")) != str(run_identity["engine"].get("vllm")):
                decisions[cid] = R_ENGINE_MISMATCH
                continue
            # identity NOT fully bound -> analysis-valid, never strict-reusable
            decisions[cid] = R_HISTORICAL_PARTIAL
            continue
        reps = rec.get("repeats") or []
        want = expected_repeats if expected_repeats is not None else \
            (int(run_identity["decoding"]["repeats"]) if run_identity else None)
        if want is not None:
            if len(reps) < want:
                decisions[cid] = R_MISSING_REPEATS
                continue
            if len(reps) > want:      # M2: exactly the expected repeats
                decisions[cid] = R_EXTRA_REPEATS
                continue
        if rec.get("status") not in (None, "complete"):
            decisions[cid] = f"REJECT_STATUS_{rec.get('status')}"
            continue
        if run_identity is None:
            # no expected identity to bind against: structure-only analysis,
            # never a strict-resume REUSABLE claim
            decisions[cid] = R_HISTORICAL_PARTIAL
            continue
        decisions[cid] = R_OK

    reusable = [cid for cid, d in decisions.items() if d == R_OK]
    missing_in_file = [cid for cid in manifest if cid not in seen_ids]
    audit = {
        "schema": "yue2-rc6-asr-receipt-audit/2",
        "transcripts_path": str(transcripts_path),
        "manifest_rows": len(manifest),
        "manifest_duplicate_ids": manifest_dupes,
        "parsed_valid_lines": len(valid_rows),
        "valid_line_indices": valid_line_indices,
        "invalid_tail_lines": tail_invalid_lines,
        "midfile_invalid_lines": midfile_invalid_lines,
        "duplicate_candidate_ids": duplicates,
        "decisions": decisions,
        "reusable": sorted(reusable),
        "rejected": sorted(c for c, d in decisions.items() if d.startswith("REJECT")),
        "incomplete": sorted(c for c, d in decisions.items() if d.startswith("INCOMPLETE")),
        "historical_partial": sorted(c for c, d in decisions.items()
                                     if d == R_HISTORICAL_PARTIAL),
        "missing_from_file": sorted(missing_in_file),
        "engine_receipt_consistent": engine_receipt is None or all(
            (_receipt_run_identity(r) or {}).get("run_identity_sha256") in
            (None, engine_receipt.get("run_identity", {}).get("run_identity_sha256"),
             engine_receipt.get("run_identity_sha256")) for r in valid_rows),
    }
    audit["fail_closed_hard_errors"] = sorted(
        set(d for d in decisions.values()
            if d.startswith("FAIL") or d == R_DUPLICATE) | (
            {R_DUPLICATE} if duplicates else set()) | (
            {R_MIDFILE_CORRUPTION} if midfile_invalid_lines else set()) | (
            {R_MANIFEST_DUPLICATES} if manifest_dupes else set()))
    audit["resume_allowed"] = (not audit["rejected"] and not duplicates
                               and not audit["fail_closed_hard_errors"])
    return audit


def quarantine_tail(transcripts_path: Path, valid_line_indices: list[int]) -> Path:
    """Bounded repair: keep the valid prefix in place, move the FULL original
    (supersede-not-overwrite) to a timestamped quarantine file next to it.

    RC6.1 M2: both writes are ATOMIC (temp file + fsync + rename) — a crash
    mid-repair can never leave a half-written transcripts file."""
    transcripts_path = Path(transcripts_path)
    import os
    import time
    q = transcripts_path.with_suffix(
        transcripts_path.suffix + f".quarantine-{time.strftime('%Y%m%dT%H%M%SZ')}")
    raw = transcripts_path.read_text().splitlines()
    keep = set(valid_line_indices)
    kept = [l for i, l in enumerate(raw) if i in keep]
    _atomic_write_text(q, "\n".join(raw) + ("\n" if raw else ""))
    _atomic_write_text(transcripts_path, "\n".join(kept) + ("\n" if kept else ""))
    return q


def _atomic_write_text(path: Path, text: str) -> None:
    import os
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def pair_strict(a: list, b: list) -> list[tuple]:
    """M2 D10: zip() silently truncates on length mismatch — this raises.

    Used by the ASR runner wherever owner/outputs (or batch/wavs) pairing
    must be exact: a silent truncation would misattribute transcripts."""
    if len(a) != len(b):
        raise ValueError(f"pair_strict: length mismatch {len(a)} != {len(b)} "
                         "(silent truncation refused)")
    return list(zip(a, b))


def verify_audio_files(manifest_rows: list[dict]) -> list[dict]:
    """M2 D11 (scorer hardening): recompute the ACTUAL audio file hashes and
    compare with the manifest-declared ones. Returns the mismatch list.

    The scorer historically compared only DECLARED hashes (transcripts vs
    manifest); a consistent lie in both passed. Files that do not exist are
    reported as {'missing': True} — the caller decides the policy (the scorer
    fails closed unless --allow-partial)."""
    out = []
    for r in manifest_rows:
        path = r.get("audio_path")
        if not path:
            continue
        p = Path(path)
        if not p.is_file():
            out.append({"id": r.get("id"), "missing": True, "path": str(p)})
            continue
        actual = sha256_file(p)
        if actual != r.get("audio_sha256"):
            out.append({"id": r.get("id"), "declared": r.get("audio_sha256"),
                        "actual": actual, "path": str(p)})
    return out


# canonical scientific identity (M2.2): content identity + execution provenance
_CRITICAL_IDENTITY_KEYS = ("model", "engine", "audio_preprocessing", "decoding")


def build_canonical_identity(*, model_root, model_files: dict, engine: dict,
                             preproc: dict, prompt_template: str | None,
                             processor_files: dict | None, decoding: dict,
                             scoring: dict, driver_sha256: str | None,
                             execution_provenance: dict | None = None) -> dict:
    """M2.2 canonical identity schema.

    scientific_content_identity = everything the MEANING of a transcript
    depends on (model files, processor/tokenizer files, engine + versions,
    preprocessing source + chunking parameters, prompt template, decoding
    settings incl. seed/dtype/batch/max_tokens/repeats, scoring identity,
    driver source). Machine-specific ABSOLUTE PATHS are deliberately kept
    OUT of the hashed content (machine moves don't change scientific
    semantics) but are preserved in execution_provenance.

    Raises ValueError when critical identity fields are missing — a missing
    field can never be accepted as a match later."""
    if not model_files:
        raise ValueError("canonical identity refuses empty model_files")
    if not prompt_template:
        raise ValueError("canonical identity requires the prompt template")
    if processor_files is None:
        raise ValueError("canonical identity requires processor/tokenizer files")
    if not driver_sha256:
        raise ValueError("canonical identity requires the driver source hash")
    for k in _CRITICAL_IDENTITY_KEYS:
        if not {k: None}.get(k) and not (engine if k == "engine" else
                                         preproc if k == "audio_preprocessing" else
                                         decoding if k == "decoding" else model_files):
            raise ValueError(f"canonical identity missing critical field: {k}")
    import hashlib
    prompt_sha = (hashlib.sha256(prompt_template.encode()).hexdigest()
                  if isinstance(prompt_template, str) else None)
    sci = {
        "model": {"files": dict(model_files)},
        "processor": {"files": dict(processor_files)},
        "engine": {k: str(v) for k, v in engine.items()},
        "audio_preprocessing": {k: (str(v) if isinstance(v, Path) else v)
                                for k, v in preproc.items()},
        "prompt_template_sha256": prompt_sha,
        "decoding": {k: str(v) for k, v in decoding.items()},
        "scoring": {k: (str(v) if isinstance(v, Path) else v) for k, v in scoring.items()},
        "driver_sha256": driver_sha256,
    }
    sci["scientific_content_identity_sha256"] = sha256_bytes(
        json.dumps(sci, sort_keys=True, ensure_ascii=False).encode())
    return {
        "schema": "yue2-rc6_1-canonical-asr-identity/1",
        "scientific_content_identity": sci,
        "execution_provenance": dict(execution_provenance or {}),
        "note": "paths live in execution_provenance only; hash over scientific content",
    }


def prepare_resume(transcripts_path: Path, manifest_rows: list[dict],
                   run_identity: dict | None = None,
                   expected_repeats: int | None = None) -> dict:
    """M2.4 durable resume — one entry point for the ASR runner.

    Sequence (all fail-closed):
      1. audit_receipts (tamper/identity/manifest/repeat checks)
      2. repairable TORN TAIL -> atomic quarantine (supersede-not-overwrite)
      3. INCOMPLETE rows (fewer repeats than expected) -> atomically moved to
         a .superseded-<ts> file; they will be re-run. This is what prevents
         the duplicate-complete-id defect: the final view keeps exactly one
         receipt per candidate.
      4. anything REJECTED / duplicated / mid-file-corrupt -> REFUSED (the
         operator starts a NEW --out path; nothing is silently deleted)

    Returns {action: READY|REFUSED, reusable, todo, superseded_file, audit}.
    """
    transcripts_path = Path(transcripts_path)
    audit = audit_receipts(transcripts_path, manifest_rows, run_identity,
                           expected_repeats)
    import time
    if audit["fail_closed_hard_errors"] or audit["rejected"]:
        return {"action": "REFUSED", "reason": "fail-closed hard errors or rejected "
                "receipts present (start a NEW --out path; supersede, never overwrite)",
                "audit": audit}
    if audit["invalid_tail_lines"]:
        quarantine_tail(transcripts_path, audit["valid_line_indices"])
        audit = audit_receipts(transcripts_path, manifest_rows, run_identity,
                               expected_repeats)
        if audit["fail_closed_hard_errors"] or audit["rejected"]:
            return {"action": "REFUSED",
                    "reason": "hard errors remained after tail quarantine", "audit": audit}
    reusable = set(audit["reusable"])
    incomplete = set(audit["incomplete"])
    superseded_file = None
    if incomplete:
        superseded_file = transcripts_path.with_suffix(
            transcripts_path.suffix + f".superseded-{time.strftime('%Y%m%dT%H%M%SZ')}")
        rows = [json.loads(l) for l in transcripts_path.read_text().splitlines()
                if l.strip()]
        keep = [r for r in rows if r["id"] not in incomplete]
        moved = [r for r in rows if r["id"] in incomplete]
        _atomic_write_text(superseded_file,
                           "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in moved))
        _atomic_write_text(transcripts_path,
                           "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
    todo = [r["id"] for r in manifest_rows if r["id"] not in reusable]
    return {"action": "READY", "reusable": sorted(reusable), "todo": todo,
            "superseded_file": str(superseded_file) if superseded_file else None,
            "audit": audit}
