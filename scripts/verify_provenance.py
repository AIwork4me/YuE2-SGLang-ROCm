#!/usr/bin/env python3
"""verify_provenance.py — C2.1 P0-C complete provenance chain audit (read-only).

Identity chain verified per journal record (new format):

  Journal record ──attempt_id──▶ Launched receipt ──attempt_id/candidate──▶
  Result receipt ──session_id──▶ Driver session receipt ──worker sha──▶
  Worker snapshot (BYTE-VERIFIED) ──driver sha──▶ (receipt-cross-checked only)

EVIDENCE LEVELS (never conflated, reported separately):
  BYTE_HASH_VERIFIED      — file bytes hashed here and matched (worker snapshots)
  RECEIPT_CROSS_CHECKED   — two independent receipts agree on the value
                            (driver sha: no driver snapshot exists by design —
                            the driver source lives in git; the verifier can
                            only prove the receipts agree, NOT that the bytes
                            are unchanged)
  RECEIPT_PRESENT         — a field exists in a receipt (e.g. session runtime
                            environment: no independent evidence on disk)
  LEGACY/UNKNOWN          — pre-C2 records without attempt ids

Per-record verdicts:
  PROVENANCE_VERIFIED   — full chain closed (all cross-checks + worker bytes)
  PROVENANCE_VIOLATION  — any break in the chain for a NEW-format record
                          (corrupt new-format records are NEVER downgraded to
                          legacy to escape verification)
  LEGACY_PROVENANCE_INCOMPLETE — old-format record (honestly unattributable
                          beyond run-level receipt, if that verifies)

Read-only guarantee: this tool opens every path O_RDONLY and never writes,
links, unlinks or chmods anything in the audited run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


class Violation(Exception):
    pass


def _load_json(path: Path, what: str) -> dict:
    if path.is_symlink():
        raise Violation(f"{what} is a symlink: {path.name}")
    if not path.is_file():
        raise Violation(f"{what} missing: {path.name}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise Violation(f"{what} corrupt JSON ({exc.msg}): {path.name}") from exc


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise Violation(msg)


def verify_record(rec: dict, prov: Path, snapshots: Path,
                  sessions_cache: dict) -> tuple[str, list[str]]:
    """Verify one NEW-format journal record against the full chain."""
    cid = rec.get("id")
    aid = rec.get("attempt_id")
    notes: list[str] = []
    _expect(isinstance(cid, str), f"journal record without candidate id")
    _expect(isinstance(aid, str) and len(aid) >= 8,
            f"{cid}: missing/short attempt_id (new-format records cannot be "
            f"downgraded to legacy)")

    launched_p = prov / cid / f"{aid}.launched.json"
    result_p = prov / cid / f"{aid}.result.json"
    launched = _load_json(launched_p, f"{cid} launched receipt")
    result = _load_json(result_p, f"{cid} result receipt")

    # --- launched <-> journal identity agreement ---
    _expect(launched.get("attempt_id") == aid, f"{cid}: launched attempt_id != journal")
    _expect(launched.get("candidate_id") == cid, f"{cid}: launched candidate_id != journal")
    for field in ("seed", "prompt_index", "candidate_index"):
        _expect(launched.get(field) == rec.get(field),
                f"{cid}: launched {field} != journal ({launched.get(field)!r} vs {rec.get(field)!r})")
    # --- result <-> launched/journal ---
    _expect(result.get("attempt_id") == aid, f"{cid}: result attempt_id != launched")
    _expect(result.get("candidate_id") == cid, f"{cid}: result candidate_id != launched")
    _expect(result.get("status") == rec.get("status"),
            f"{cid}: result status {result.get('status')!r} != journal {rec.get('status')!r}")
    for field in ("seed", "prompt_index", "candidate_index"):
        _expect(result.get(field) == rec.get(field),
                f"{cid}: result {field} != journal")
    for field in ("worker_source_sha256", "driver_source_sha256", "session_id"):
        lv, rv, jv = launched.get(field), result.get(field), rec.get(field)
        _expect(lv is not None and lv == rv == jv,
                f"{cid}: {field} disagrees across receipts/journal "
                f"({lv!r}/{rv!r}/{jv!r})")

    # --- driver session receipt ---
    sid = rec.get("session_id")
    _expect(isinstance(sid, str) and len(sid) >= 8, f"{cid}: missing session_id")
    if sid not in sessions_cache:
        sessions_cache[sid] = _load_json(
            prov / "driver_sessions" / f"{sid}.json", f"driver session {sid[:8]}…")
    session = sessions_cache[sid]
    _expect(session.get("session_id") == sid, f"{cid}: session receipt id mismatch")
    _expect(session.get("worker_source_sha256") == rec.get("worker_source_sha256"),
            f"{cid}: session worker sha != attempt")
    _expect(session.get("driver_source_sha256") == rec.get("driver_source_sha256"),
            f"{cid}: session driver sha != attempt")
    runtime = session.get("runtime")
    _expect(isinstance(runtime, dict) and runtime.get("python"),
            f"{cid}: session runtime identity absent (environment evidence)")

    # --- worker snapshot: BYTE verification (the only byte-level proof) ---
    ws = rec.get("worker_source_sha256")
    _expect(isinstance(ws, str) and len(ws) == 64, f"{cid}: worker sha malformed")
    snap = snapshots / f"{ws}.py"
    _expect(not snap.is_symlink(), f"{cid}: worker snapshot is a symlink")
    _expect(snap.is_file(), f"{cid}: worker snapshot missing {ws[:12]}…")
    _expect(sha(snap) == ws, f"{cid}: worker snapshot tampered {ws[:12]}…")

    # driver sha: receipt-cross-checked only (no driver snapshot by design)
    ds = rec.get("driver_source_sha256")
    _expect(isinstance(ds, str) and len(ds) == 64, f"{cid}: driver sha malformed")
    notes.append("driver_source_sha256: RECEIPT_CROSS_CHECKED_ONLY "
                 "(driver source is git-managed; no on-disk snapshot)")
    return "PROVENANCE_VERIFIED", notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    args = ap.parse_args()
    runs = args.runs
    journal_path = runs / "generation_manifest.jsonl"
    if not journal_path.is_file():
        print("::error::no generation_manifest.jsonl", file=sys.stderr)
        return 2
    rows = [json.loads(l) for l in journal_path.read_text().splitlines() if l.strip()]
    snapshots = runs / "worker_sources"
    prov = runs / "provenance"
    legacy_worker = runs / "_gen_worker.py"
    run_worker_sha = None
    rc = runs / "run_config.json"
    if rc.is_file():
        run_worker_sha = json.loads(rc.read_text()).get("generator_worker_sha256")

    verdicts: Counter = Counter()
    violations: list[str] = []
    notes: set[str] = set()
    attempt_ids: set[str] = set()
    sessions_cache: dict = {}
    has_provenance_tree = prov.is_dir()
    # The old driver writes a contiguous LEGACY prefix; the new driver adds
    # attempt/session fields to every appended record. A candidate may appear
    # in both eras (legacy failed -> new-format retry), so existence of its
    # current provenance directory alone does NOT make the old prefix corrupt.
    # Conversely, an unmarked row after the first new-format event is unsafe:
    # without a trusted pre-upgrade prefix it could be a stripped new record.
    provenance_markers = (
        "attempt_id", "worker_source_sha256", "driver_source_sha256", "session_id"
    )
    first_new_index = next(
        (i for i, row in enumerate(rows)
         if any(k in row for k in provenance_markers)), len(rows)
    )
    new_positions_by_id: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        if any(k in row for k in provenance_markers) and isinstance(
                row.get("attempt_id"), str):
            new_positions_by_id.setdefault(row.get("id"), []).append(i)
    legacy_mixed_history = 0
    for n, rec in enumerate(rows, 1):
        if rec.get("attempt_id") is None:
            # OLD vs CORRUPT-NEW distinction: a record that carries any
            # provenance field, or whose candidate HAS attempt receipts on
            # disk, is a NEW-FORMAT record — a missing attempt_id in it is
            # DAMAGE, not legacy history (never downgraded to escape checks).
            new_format_markers = any(
                k in rec for k in provenance_markers)
            if new_format_markers:
                violations.append(
                    f"line {n} ({rec.get('id')}): new-format record missing "
                    f"attempt_id (has provenance fields) — corruption, not legacy")
                verdicts["PROVENANCE_VIOLATION"] += 1
                continue
            if n - 1 >= first_new_index:
                violations.append(
                    f"line {n} ({rec.get('id')}): unmarked record after "
                    f"new-format cutover — cannot establish legacy origin")
                verdicts["PROVENANCE_VIOLATION"] += 1
                continue
            if has_provenance_tree and isinstance(rec.get("id"), str) \
                    and (prov / rec["id"]).is_dir():
                # A historical pre-upgrade failure and a *later journaled*
                # new-format retry of this SAME candidate legitimately coexist.
                # The newer attempt's receipts are independently checked below.
                # An unjournaled attempt directory is NOT sufficient evidence.
                later = new_positions_by_id.get(rec["id"], [])
                if not any(i > n - 1 for i in later):
                    violations.append(
                        f"line {n} ({rec.get('id')}): attempt receipts exist "
                        f"on disk but no later journaled new-format retry — "
                        f"cannot establish unmodified legacy origin")
                    verdicts["PROVENANCE_VIOLATION"] += 1
                    continue
                legacy_mixed_history += 1
            attributed = "UNKNOWN"
            if legacy_worker.is_file():
                lsha = sha(legacy_worker)
                if run_worker_sha and lsha == run_worker_sha:
                    attributed = f"LEGACY_RUN_LEVEL_VERIFIED({lsha[:12]}…)"
                else:
                    attributed = f"LEGACY_MISMATCH({lsha[:12]}… vs run-level)"
            verdicts["LEGACY_PROVENANCE_INCOMPLETE"] += 1
            continue
        if rec.get("attempt_id") in attempt_ids:
            violations.append(f"line {n} ({rec.get('id')}): duplicate attempt_id")
            verdicts["PROVENANCE_VIOLATION"] += 1
            continue
        attempt_ids.add(rec.get("attempt_id"))
        try:
            verdict, rec_notes = verify_record(rec, prov, snapshots,
                                               sessions_cache)
            verdicts[verdict] += 1
            notes.update(rec_notes)
        except Violation as exc:
            violations.append(f"line {n} ({rec.get('id')}): {exc}")
            verdicts["PROVENANCE_VIOLATION"] += 1

    # --- orphan attempt receipts: crash-before-journal / crash-after-commit ---
    # A complete-STATUS result receipt with NO journal record means the
    # journal undercounts the campaign -> integrity violation. A launched-only
    # orphan is honest crash forensics -> reported as notes, not violations.
    orphan_complete: list[str] = []
    orphan_launched: list[str] = []
    orphan_result_only: list[str] = []
    journal_attempt_ids = {
        row.get("attempt_id") for row in rows
        if isinstance(row.get("attempt_id"), str)
    }
    if prov.is_dir():
        for cand_dir in sorted(prov.iterdir()):
            if cand_dir.name == "driver_sessions":
                continue
            if cand_dir.is_symlink():
                orphan_result_only.append(f"{cand_dir.name}/SYMLINK_DIR")
                continue
            if not cand_dir.is_dir():
                continue
            # A RESULT-only receipt is never a valid crash window: every
            # result must have a launched counterpart. If it has a journal
            # row, verify_record already reports that missing launched receipt.
            # For an unjournaled result we must detect it explicitly, rather
            # than only iterating "*.launched.json" as the old code did.
            for result_f in cand_dir.glob("*.result.json"):
                aid = result_f.name.removesuffix(".result.json")
                if (aid not in journal_attempt_ids and not
                        (cand_dir / f"{aid}.launched.json").is_file()):
                    orphan_result_only.append(
                        f"{cand_dir.name}/{aid[:8]}…")
            for launched_f in cand_dir.glob("*.launched.json"):
                aid = launched_f.name.split(".")[0]
                journal_has = aid in journal_attempt_ids
                if journal_has:
                    continue
                result_f = cand_dir / f"{aid}.result.json"
                if result_f.is_file():
                    try:
                        rstat = json.loads(result_f.read_text()).get("status")
                    except json.JSONDecodeError:
                        rstat = "corrupt"
                    if rstat == "complete":
                        orphan_complete.append(f"{cand_dir.name}/{aid[:8]}…")
                    else:
                        orphan_launched.append(f"{cand_dir.name}/{aid[:8]}…")
                else:
                    orphan_launched.append(f"{cand_dir.name}/{aid[:8]}…")
    for o in orphan_complete:
        violations.append(
            f"orphan COMPLETE attempt receipt without journal record: {o} "
            f"(crash after artifact commit — journal undercounts)")
    for o in orphan_result_only:
        violations.append(
            f"result-only orphan receipt without launched/journal: {o} "
            f"(unverifiable provenance, never silently ignored)")
    verdicts["PROVENANCE_VIOLATION"] += (
        len(orphan_complete) + len(orphan_result_only)
    )

    summary = {
        "run": str(runs),
        "journal_records": len(rows),
        "verdicts": dict(verdicts),
        "distinct_attempts": len(attempt_ids),
        "distinct_sessions": len(sessions_cache),
        "orphan_launched_only_attempts": len(orphan_launched),
        "orphan_result_only_attempts": len(orphan_result_only),
        "legacy_mixed_history_records": legacy_mixed_history,
        "legacy_prefix_boundary": first_new_index,
        "evidence_levels": {
            "worker_snapshot": "BYTE_HASH_VERIFIED (sha256 recomputed on disk)",
            "driver_source_sha256": ("RECEIPT_CROSS_CHECKED_ONLY — receipts agree; "
                                     "no on-disk driver snapshot exists by design"),
            "session_runtime": "RECEIPT_PRESENT (no independent on-disk evidence)",
            "legacy_records": "UNKNOWN beyond run-level receipt (if it verifies)",
        },
    }
    print(json.dumps(summary, indent=2))
    for v in violations[:60]:
        print("::error::" + v, file=sys.stderr)
    if verdicts["PROVENANCE_VIOLATION"]:
        print(f"FAIL: {verdicts['PROVENANCE_VIOLATION']} provenance violations",
              file=sys.stderr)
        return 1
    print("PASS: no provenance violations "
          f"({verdicts['LEGACY_PROVENANCE_INCOMPLETE']} legacy records honestly "
          "marked; evidence levels reported separately, never conflated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
