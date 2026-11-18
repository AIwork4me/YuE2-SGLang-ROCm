#!/usr/bin/env python3
"""restoration_audit.py — strict audit of a RESTORED campaign subset (C1).

Problem this solves: verify_wsb_artifacts.py derives its expected set from the
run's evaluation_inputs.jsonl (write-once, 384 rows for a full campaign). On a
restored-at-177 state that auditor reports 207 "missing" problems — the correct
FULL-campaign semantics, but useless as a RESTORATION gate. The old handoff's
`--mode pilot --expect 354` advice is wrong twice over (pilot --expect must
equal the selection size, and the selection still contains all 384 rows).

This tool NEVER edits the campaign's frozen inputs. Its verification set is
the restored journal's DISTINCT COMPLETE ids (the only things that can be
restored-audited), and every id must independently survive:

  1. frozen dataset revision pin (reproduction_manifest.jsonl sha256);
  2. membership + seed fidelity vs the run's (read-only) evaluation_inputs
     and the frozen manifest's candidate_ar_seeds;
  3. the OFFICIAL verify_result on the actual bundle (not journal claims);
  4. request contract checks (seed / cot / cfg_scale);
  5. identity recompute (recorded identity == recomputed request/config/weights);
  6. unresolved-failure scan of the journal (a failed id without a later
     complete record blocks the verdict);
  7. an INDEPENDENT temp workspace (symlink farm + filtered inputs) on which
     the official verify_wsb_artifacts.py --mode pilot --expect <n> must
     return verdict PILOT with zero problems — proving the official auditor
     itself accepts the restored subset when fed an honest subset selection;
  8. optional cross-check vs the git-frozen generation manifest snapshot
     (--snapshot evidence/publication/fresh_image/armA/
      generation_manifest_snapshot_20261116T1145Z.jsonl).

Verdict vocabulary: RESTORED_SUBSET_VERIFIED (n/total) or RESTORE_BLOCKED.
A subset verdict is NEVER a campaign-completion claim; exit 0 only on
RESTORED_SUBSET_VERIFIED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_wsb_artifacts import sha256_file, recompute_identity  # noqa: E402
from run_wsb_torch import read_journal  # noqa: E402
from yue2_workspace import resolve_workspace  # noqa: E402

MANIFEST_SHA256 = "859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0"


def _resolve_verify_result(ws: Path):
    """Official frozen checker, same resolution order as the campaign auditor."""
    for p in (ws / "benchmark" / "wsb_metrics",
              ws / "benchmark" / "WildSongBench" / "wsb_metrics",
              ws / "benchmark" / "WildSongBench" / "evaluation" / "wsb_metrics"):
        if (p / "artifact_storage.py").is_file():
            sys.path.insert(0, str(p))
            break
    from artifact_storage import verify_result  # official frozen checker
    return verify_result


def row_ident(row: dict) -> str:
    seed = row["seed"]
    return f"wsb_{row['prompt_index']:03d}_r{row['candidate_index']}_s{seed}"


def load_run_inputs(run_dir: Path) -> list[dict]:
    inputs = run_dir / "evaluation_inputs.jsonl"
    if not inputs.is_file():
        raise SystemExit(f"FATAL: {inputs} missing (restored run incomplete)")
    rows = [json.loads(l) for l in inputs.read_text().splitlines() if l.strip()]
    return rows


def unresolved_failures(journal_path: Path, complete: set[str]) -> list[str]:
    failed: set[str] = set()
    if not journal_path.is_file():
        return []
    for line in journal_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("status") == "failed" and rec.get("id"):
            failed.add(rec["id"])
    return sorted(failed - complete)


def build_subset_inputs_text(rows: list[dict], complete_ids: set[str]) -> tuple[str, int]:
    kept = [r for r in rows if row_ident(r) in complete_ids]
    return "".join(json.dumps(r) + "\n" for r in kept), len(kept)


def make_audit_workspace(tmp_root: Path, run_dir: Path, rows: list[dict],
                         complete_ids: set[str]) -> Path:
    """Independent PILOT workspace: symlinked bundles + honest subset inputs.

    The original campaign dir is never written to by the pilot run (the
    official auditor writes audit.json into ITS --runs argument, which is this
    temp dir).
    """
    ws_dir = tmp_root / time.strftime("restoration_audit_%Y%m%dT%H%M%SZ")
    (ws_dir / "songs").mkdir(parents=True)
    text, _ = build_subset_inputs_text(rows, complete_ids)
    (ws_dir / "evaluation_inputs.jsonl").write_text(text)
    src_songs = run_dir / "songs"
    for ident in sorted(complete_ids):
        target = src_songs / ident
        if not target.is_dir():
            continue
        (ws_dir / "songs" / ident).symlink_to(target.resolve())
    return ws_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True,
                    help="restored campaign dir (read-only for frozen inputs)")
    ap.add_argument("--expect-complete", type=int, default=None,
                    help="expected number of distinct complete ids (e.g. 177)")
    ap.add_argument("--snapshot", type=Path, default=None,
                    help="git-frozen generation manifest snapshot to cross-check")
    ap.add_argument("--auditor-python", default=None,
                    help="interpreter for the official pilot audit "
                         "(default: env A python if present, else sys.executable)")
    ap.add_argument("--keep-workspace", action="store_true",
                    help="keep the temp pilot workspace for inspection")
    args = ap.parse_args()
    runs: Path = args.runs
    tmp_root = Path(os.environ.get("YUE2_WORKSPACE", "/data/yue2")) / "tmp"

    problems: list[str] = []
    warnings: list[str] = []
    t0 = time.time()

    ws = resolve_workspace(str(REPO / "scripts/campaign_ops/restoration_audit.py"))
    manifest_path = ws / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
    if not manifest_path.is_file():
        print(f"FATAL: manifest not found: {manifest_path}")
        return 2
    msha = sha256_file(manifest_path)
    if msha != MANIFEST_SHA256:
        print(f"FATAL: dataset revision mismatch: {msha} != {MANIFEST_SHA256}")
        return 2
    manifest_rows = [json.loads(l) for l in manifest_path.read_text().splitlines() if l.strip()]
    rows_by_index = {r["prompt_index"]: r for r in manifest_rows}

    # --- restored set: journal distinct complete ids
    journal_path = runs / "generation_manifest.jsonl"
    if not journal_path.is_file():
        print(f"FATAL: {journal_path} missing (restored run incomplete)")
        return 2
    complete, journal_problems = read_journal(journal_path)
    for p in journal_problems:
        warnings.append(f"journal: {p}")

    # --- run identity cross-check (read-only)
    run_config = runs / "run_config.json"
    if run_config.is_file():
        rc = json.loads(run_config.read_text())
        if rc.get("driver_protocol") != "armA-driver/1":
            problems.append(f"run_config driver_protocol {rc.get('driver_protocol')!r} "
                            "!= 'armA-driver/1'")
        if rc.get("manifest_sha256") != MANIFEST_SHA256:
            problems.append("run_config manifest_sha256 != frozen pin")
    else:
        problems.append("run_config.json missing")

    rows = load_run_inputs(runs)
    by_ident = {row_ident(r): r for r in rows}
    if len(by_ident) != len(rows):
        problems.append("evaluation_inputs.jsonl contains duplicate identities")
    total_expected = len(rows)

    for ident in sorted(complete):
        row = by_ident.get(ident)
        if row is None:
            problems.append(f"{ident}: complete id not present in evaluation_inputs")
            continue
        i, j, seed = row["prompt_index"], row["candidate_index"], row["seed"]
        official_seed = rows_by_index[i]["candidate_ar_seeds"][j]
        if seed != official_seed:
            problems.append(f"{ident}: seed {seed} != frozen manifest {official_seed}")

    unresolved = unresolved_failures(journal_path, complete)
    for ident in unresolved:
        problems.append(f"{ident}: unresolved failed record without later complete")

    partials = sorted(p.name for p in (runs / "songs").glob("*.partial*")
                      if (runs / "songs").is_dir())
    if partials:
        warnings.append(f"{len(partials)} .partial residue dirs (quarantined on "
                        "regeneration; listed in report)")

    # --- per-candidate official verification
    verify_result = _resolve_verify_result(ws)
    verified = 0
    for ident in sorted(complete):
        cand = runs / "songs" / ident
        if not (cand / "result.json").is_file():
            problems.append(f"{ident}: journal complete but bundle missing")
            continue
        try:
            r = verify_result(cand)
        except Exception as exc:
            problems.append(f"{ident}: official verify_result FAILED: "
                            f"{type(exc).__name__}: {exc}")
            continue
        row = by_ident.get(ident)
        if row is not None:
            req_path = cand / "request.json"
            if not req_path.is_file():
                problems.append(f"{ident}: missing request.json")
                continue
            req = json.loads(req_path.read_text())
            if req.get("seed") != row["seed"]:
                problems.append(f"{ident}: request seed {req.get('seed')} "
                                f"!= official {row['seed']}")
            if req.get("cot") != "full":
                problems.append(f"{ident}: request cot {req.get('cot')!r} != 'full'")
            if req.get("cfg_scale") not in (1.0, None):
                problems.append(f"{ident}: request cfg_scale {req.get('cfg_scale')} "
                                "not 1.0/None")
        recorded = r.get("identity")
        recomputed = recompute_identity(cand)
        if recomputed is None or recorded != recomputed:
            problems.append(f"{ident}: identity recheck FAILED")
        else:
            verified += 1

    # --- optional snapshot cross-check
    if args.snapshot is not None and Path(args.snapshot).is_file():
        snap_ids = set()
        for line in Path(args.snapshot).read_text().splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("status") == "complete":
                snap_ids.add(rec["id"])
        if snap_ids != complete:
            only_journal = sorted(complete - snap_ids)
            only_snap = sorted(snap_ids - complete)
            problems.append(f"snapshot cross-check FAILED: journal-only "
                            f"{len(only_journal)} {only_journal[:5]}, snapshot-only "
                            f"{len(only_snap)} {only_snap[:5]}")

    # --- independent official PILOT audit on the subset
    pilot_ok = None
    pilot_ws = None
    auditor_py = args.auditor_python
    if auditor_py is None:
        env_a = ws / "environments/yue2-torch/bin/python"
        auditor_py = str(env_a) if env_a.is_file() else sys.executable
    if complete and not problems:
        tmp_root.mkdir(parents=True, exist_ok=True)
        pilot_ws = make_audit_workspace(tmp_root, runs, rows, complete)
        r = subprocess.run(
            [auditor_py, str(REPO / "scripts/verify_wsb_artifacts.py"),
             "--runs", str(pilot_ws), "--mode", "pilot",
             "--expect", str(len(complete))],
            capture_output=True, text=True, timeout=3600)
        (pilot_ws / "official_pilot_stdout.log").write_text(
            r.stdout + "\n--- stderr ---\n" + r.stderr)
        pilot_ok = r.returncode == 0
        if not pilot_ok:
            problems.append("official pilot audit on the restored subset did not "
                            "pass (see official_pilot_stdout.log in the temp ws)")
    elif not complete:
        problems.append("journal contains zero complete ids")

    if args.expect_complete is not None and len(complete) != args.expect_complete:
        problems.append(f"expected {args.expect_complete} complete ids, "
                        f"journal has {len(complete)}")

    verdict = ("RESTORED_SUBSET_VERIFIED"
               if complete and not problems and verified == len(complete)
               and pilot_ok is True else "RESTORE_BLOCKED")

    report = {
        "tool": "restoration_audit.py",
        "runs": str(runs),
        "audit_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "journal_distinct_complete": len(complete),
        "official_verify_result_passed": verified,
        "evaluation_inputs_total": total_expected,
        "restored_fraction": f"{len(complete)}/{total_expected}",
        "snapshot_crosscheck": str(args.snapshot) if args.snapshot else None,
        "pilot_workspace": str(pilot_ws) if pilot_ws else None,
        "pilot_passed": pilot_ok,
        "partial_residues": partials,
        "warning_count": len(warnings),
        "warnings": warnings,
        "problem_count": len(problems),
        "problems": problems,
        "verdict": verdict,
        "verdict_detail": (f"{verdict}: {len(complete)} of {total_expected} "
                           f"candidates independently verified "
                           f"(subset verdict; NOT a campaign-completion claim)"),
        "wall_s": round(time.time() - t0, 1),
    }
    out = runs / "restoration_audit.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("problems", "warnings")}, indent=2))
    if problems:
        print(f"problems ({len(problems)}):")
        for p in problems:
            print(" -", p)
    if pilot_ws and not args.keep_workspace and verdict == "RESTORED_SUBSET_VERIFIED":
        shutil.rmtree(pilot_ws, ignore_errors=True)
    return 0 if verdict == "RESTORED_SUBSET_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
