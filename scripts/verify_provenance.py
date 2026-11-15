#!/usr/bin/env python3
"""verify_provenance.py — C2 P3 provenance consistency audit.

For every journal record in a run directory, establish one of:
  PROVENANCE_VERIFIED   — attempt receipts exist; worker/driver shas match the
                          journal; the worker snapshot exists and hash-verifies
  LEGACY_PROVENANCE_INCOMPLETE — record predates per-attempt provenance (no
                          attempt_id); worker attribution falls back to the
                          run-level receipt ONLY if the legacy `_gen_worker.py`
                          hash-verifies against it, else UNKNOWN
  PROVENANCE_VIOLATION  — receipts conflict, snapshots tampered/symlinked,
                          duplicate attempt ids, or journal/receipt mismatch

Verdicts are per-record and summarized. Exit 0 only when zero VIOLATIONS
(LEGACY_INCOMPLETE is honest history, not a violation — it is reported).
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


def read_journal(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    args = ap.parse_args()
    runs = args.runs
    journal_path = runs / "generation_manifest.jsonl"
    if not journal_path.is_file():
        print("::error::no generation_manifest.jsonl", file=sys.stderr)
        return 2
    rows = read_journal(journal_path)
    snapshots = runs / "worker_sources"
    prov = runs / "provenance"
    legacy_worker = runs / "_gen_worker.py"
    run_config = (runs / "run_config.json")
    run_worker_sha = None
    if run_config.is_file():
        run_worker_sha = json.loads(run_config.read_text()).get(
            "generator_worker_sha256")

    verdicts: Counter = Counter()
    violations: list[str] = []
    attempt_ids: set[str] = set()
    for n, rec in enumerate(rows, 1):
        cid = rec.get("id")
        aid = rec.get("attempt_id")
        status = rec.get("status")
        if aid is None:
            # legacy record: attribute ONLY if a verified legacy source exists
            attributed = "UNKNOWN"
            if legacy_worker.is_file():
                lsha = sha(legacy_worker)
                if run_worker_sha and lsha == run_worker_sha:
                    attributed = f"LEGACY_RUN_LEVEL_VERIFIED({lsha[:12]}…)"
                else:
                    attributed = f"LEGACY_MISMATCH({lsha[:12]}… vs run-level)"
            verdicts["LEGACY_PROVENANCE_INCOMPLETE"] += 1
            continue
        if aid in attempt_ids:
            violations.append(f"line {n} ({cid}): duplicate attempt_id {aid}")
            verdicts["PROVENANCE_VIOLATION"] += 1
            continue
        attempt_ids.add(aid)
        launched = prov / cid / f"{aid}.launched.json"
        result = prov / cid / f"{aid}.result.json"
        problems = []
        if not launched.is_file():
            problems.append("launched receipt missing")
        else:
            try:
                lrec = json.loads(launched.read_text())
                if lrec.get("worker_source_sha256") != rec.get("worker_source_sha256"):
                    problems.append("worker sha: launched receipt != journal")
                if lrec.get("driver_source_sha256") != rec.get("driver_source_sha256"):
                    problems.append("driver sha: launched receipt != journal")
                if lrec.get("candidate_id") != cid:
                    problems.append("launched receipt candidate mismatch")
            except json.JSONDecodeError:
                problems.append("launched receipt unparseable")
            ws = rec.get("worker_source_sha256")
            if ws:
                snap = snapshots / f"{ws}.py"
                if snap.is_symlink():
                    problems.append("worker snapshot is a symlink")
                elif not snap.is_file():
                    problems.append(f"worker snapshot missing {ws[:12]}…")
                elif sha(snap) != ws:
                    problems.append(f"worker snapshot tampered {ws[:12]}…")
        if result.is_file():
            try:
                rrec = json.loads(result.read_text())
                if rrec.get("status") != status:
                    problems.append("result receipt status != journal")
                if rrec.get("session_id") != rec.get("session_id"):
                    problems.append("result receipt session != journal")
            except json.JSONDecodeError:
                problems.append("result receipt unparseable")
        elif status in ("complete", "failed"):
            problems.append("result receipt missing (crash before commit?)")
        if problems:
            violations.append(f"line {n} ({cid}, attempt {aid[:8]}…): "
                              + "; ".join(problems))
            verdicts["PROVENANCE_VIOLATION"] += 1
        else:
            verdicts["PROVENANCE_VERIFIED"] += 1

    print(json.dumps({
        "run": str(runs),
        "journal_records": len(rows),
        "verdicts": dict(verdicts),
        "distinct_attempts": len(attempt_ids),
    }, indent=2))
    for v in violations[:60]:
        print("::error::" + v, file=sys.stderr)
    if verdicts["PROVENANCE_VIOLATION"]:
        print(f"FAIL: {verdicts['PROVENANCE_VIOLATION']} provenance violations",
              file=sys.stderr)
        return 1
    print("PASS: no provenance violations "
          f"({verdicts['LEGACY_PROVENANCE_INCOMPLETE']} legacy records "
          "honestly marked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
