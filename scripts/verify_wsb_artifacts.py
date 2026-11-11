#!/usr/bin/env python3
"""verify_wsb_artifacts.py v3 - strict WSB run auditor (gfx1100/gfx1151 portable).

v3 restores the schema produced by the campaign-machine auditor
(evidence/final_generation_audit.json: classification, identity_reverified,
expected_prompt_indices) while keeping every v2 strictness guarantee:

  - FULL MODE CAN NO LONGER SILENTLY REDUCE ITS EXPECTED COUNT. `--mode full`
    (default) requires exactly 384 verified candidates, 192 unique prompts,
    exactly candidates {0,1} per prompt. `--expect` is cross-checked, never
    used to lower the bar.
  - NO ERROR-LIST RESET: every problem accumulates from the start.
  - Detects: missing candidates ("missing (no candidate directory)"), wrong
    seeds vs the frozen manifest and inside request.json ("seed X != official
    Y"), duplicate candidate identities and duplicate selection rows,
    UNEXPECTED candidate dirs, failed official verify_result (reported as
    "artifact integrity FAILED"), forged self-consistent bundles (identity
    recompute), driver journal cross-check (generation_failed stays an open
    defect; finalize_failed with a now-verifying bundle is classified as
    recovered), wrong dataset revision (manifest row hash), truncated-but-
    valid (allowed, counted).
  - `--mode pilot` is the ONLY way to audit a subset; it still enforces
    manifest-seed fidelity and full per-candidate verification for the subset
    it was given, and clearly labels the verdict PILOT (never FULL).

Usage:
  python scripts/verify_wsb_artifacts.py --runs runs/gfx1100/<id>/wsb_full            # strict 384
  python scripts/verify_wsb_artifacts.py --runs runs/gfx1100/<id>/pilot --mode pilot
Exit 0 only on verdict FULL (or PILOT with zero problems).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from yue2_workspace import resolve_workspace

try:
    WS = resolve_workspace(__file__)
except FileNotFoundError:
    WS = None  # unit-test import safety; strict re-resolution happens in main()
MANIFEST_PATH = (WS or Path(".")) / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
MANIFEST_SHA256 = "859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0"

if WS is not None:
    for _p in (WS / "benchmark" / "wsb_metrics",
               WS / "benchmark" / "WildSongBench" / "wsb_metrics",
               WS / "benchmark" / "WildSongBench" / "evaluation" / "wsb_metrics"):
        if (_p / "artifact_storage.py").is_file():
            sys.path.insert(0, str(_p))
            break
try:
    from artifact_storage import verify_result  # official frozen checker
except ImportError:  # pragma: no cover - workspace absent (unit-test import)
    verify_result = None

REQUIRED_ARTIFACTS = {"audio.flac", "prefix.npy", "semantic.npy", "latent.npy",
                      "request.json", "config.json"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def recompute_identity(cand: Path) -> str | None:
    """Recompute the finalize_candidate identity blob hash (request+config+weights).

    Returns None when the inputs to the identity are unreadable; the caller
    reports it as an unverifiable identity instead of guessing.
    """
    try:
        result = json.loads((cand / "result.json").read_text())
        request = json.loads((cand / "request.json").read_text())
        config = json.loads((cand / "config.json").read_text())
        weights = result.get("weights")
        blob = json.dumps({"request": request, "config": config, "weights": weights},
                          ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(blob.encode()).hexdigest()
    except Exception:
        return None


def main() -> int:
    global WS, MANIFEST_PATH
    if WS is None:
        WS = resolve_workspace(__file__)
        MANIFEST_PATH = WS / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--mode", choices=("full", "pilot"), default="full")
    ap.add_argument("--expect", type=int, default=None,
                    help="full mode: must equal 384; pilot: exact subset size "
                         "(default: 384 for full mode, selection size for pilot)")
    ap.add_argument("--allow-missing-dataset-hash", action="store_true",
                    help="record (not ignore) a manifest hash mismatch instead of failing")
    args = ap.parse_args()

    problems: list[str] = []          # NEVER reset after starting
    results: dict[tuple[int, int], dict] = {}
    classification: Counter = Counter()
    identity_reverified = 0

    # 0) frozen dataset revision check
    if not MANIFEST_PATH.is_file():
        print(f"FATAL: manifest not found: {MANIFEST_PATH}")
        return 2
    manifest_sha = sha256_file(MANIFEST_PATH)
    dataset_ok = manifest_sha == MANIFEST_SHA256
    if not dataset_ok:
        msg = (f"dataset revision mismatch: reproduction_manifest.jsonl sha256 {manifest_sha} "
               f"!= frozen pin {MANIFEST_SHA256}")
        if args.allow_missing_dataset_hash:
            problems.append(f"WARNING-RECORDED: {msg}")
        else:
            print(f"FATAL: {msg}")
            return 2

    rows = [json.loads(l) for l in MANIFEST_PATH.read_text().splitlines() if l.strip()]
    if not (len(rows) == 192 and [r["prompt_index"] for r in rows] == list(range(192))):
        print("FATAL: frozen manifest shape violated (192 rows, contiguous 0..191)")
        return 2
    rows_by_index = {r["prompt_index"]: r for r in rows}

    # 1) expected set from the run's evaluation_inputs.jsonl (authoritative
    #    record of what THIS run set out to generate)
    inputs_path = args.runs / "evaluation_inputs.jsonl"
    if not inputs_path.is_file():
        print(f"FATAL: {inputs_path} missing (run driver must create it first)")
        return 2
    selected = [json.loads(l) for l in inputs_path.read_text().splitlines() if l.strip()]
    if args.expect is None:
        args.expect = 384 if args.mode == "full" else len(selected)

    expected: dict[tuple[int, int], tuple[int, str]] = {}
    seen_pairs: Counter = Counter()
    for e in selected:
        i, j, seed = e.get("prompt_index"), e.get("candidate_index"), e.get("seed")
        if not isinstance(i, int) or not (0 <= i < 192):
            problems.append(f"evaluation_inputs: bad prompt_index {i!r}")
            continue
        if j not in (0, 1):
            problems.append(f"evaluation_inputs: candidate_index must be 0 or 1, got {j!r} (row {i})")
            continue
        row = rows_by_index[i]
        if row["candidate_ar_seeds"][j] != seed:
            problems.append(f"({i},{j}): seed {seed} != frozen manifest seed "
                            f"{row['candidate_ar_seeds'][j]}")
            continue
        seen_pairs[(i, j)] += 1
        expected[(i, j)] = (seed, f"wsb_{i:03d}_r{j}_s{seed}")

    for pair, n in seen_pairs.items():
        if n > 1:
            problems.append(f"evaluation_inputs: duplicate (prompt_index, candidate_index) "
                            f"{pair} ({n}x)")

    if args.mode == "full":
        if args.expect != 384:
            problems.append(f"full mode requires --expect 384, got {args.expect} "
                            f"(REFUSING to lower the bar)")
        if len(expected) != 384:
            problems.append(f"full mode expected exactly 384 unique candidates, "
                            f"got {len(expected)} (REFUSING to lower the bar)")
        prompts = {i for (i, _) in expected}
        if prompts != set(range(192)):
            missing_p = sorted(set(range(192)) - prompts)
            extra_p = sorted(prompts - set(range(192)))
            problems.append(f"full mode prompt coverage broken: {len(prompts)} unique "
                            f"(missing {len(missing_p)}: {missing_p[:8]}...; "
                            f"unexpected {extra_p[:8]})")
        for i in sorted(prompts):
            js = sorted(j for (ii, j) in expected if ii == i)
            if js != [0, 1]:
                problems.append(f"prompt {i}: candidates {js} != [0, 1]")
    else:  # pilot: --expect must match the selection exactly, never adjusted
        if args.expect != len(expected):
            problems.append(f"pilot mode --expect {args.expect} != selection size "
                            f"{len(expected)} (never adjusted silently)")

    # 2) driver journal cross-check (generation_manifest.jsonl)
    journal: dict[str, str] = {}
    journal_path = args.runs / "generation_manifest.jsonl"
    if journal_path.is_file():
        for line in journal_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                journal[row.get("id")] = row.get("status")
            except Exception:
                problems.append("generation_manifest.jsonl: unparseable row")
        for ident, status in journal.items():
            if status == "generation_failed":
                classification["driver:generation_failed"] += 1
            elif status == "finalize_failed":
                classification["driver:finalize_failed"] += 1

    # 3) per-candidate official verification
    songs = args.runs / "songs"
    if not songs.is_dir():
        print(f"FATAL: {songs} missing")
        return 2
    for key, (seed, ident) in sorted(expected.items()):
        cand = songs / ident
        if not (cand / "result.json").is_file():
            if journal.get(ident) == "generation_failed":
                problems.append(f"{ident}: driver status 'generation_failed' "
                                f"(unrecovered; missing bundle)")
            else:
                problems.append(f"{ident}: missing (no candidate directory)")
            continue
        try:
            r = verify_result(cand)
        except Exception as exc:
            problems.append(f"{ident}: artifact integrity FAILED: "
                            f"{type(exc).__name__}: {exc}")
            continue
        req_path = cand / "request.json"
        if not req_path.is_file():
            problems.append(f"{ident}: missing request.json")
            continue
        req = json.loads(req_path.read_text())
        if req.get("seed") != seed:
            problems.append(f"{ident}: request seed {req.get('seed')} != official {seed}")
        if req.get("cot") != "full":
            problems.append(f"{ident}: request cot {req.get('cot')!r} != 'full'")
        if req.get("cfg_scale") not in (1.0, None):
            problems.append(f"{ident}: request cfg_scale {req.get('cfg_scale')} not 1.0/None")
        # identity re-verification: a forged-but-self-consistent bundle must
        # still fail the recomputed request/config/weights identity check.
        recorded = r.get("identity")
        recomputed = recompute_identity(cand)
        if recomputed is None or recorded != recomputed:
            problems.append(f"{ident}: identity recheck FAILED (recorded identity does not "
                            f"match recomputed request/config/weights hash)")
        else:
            identity_reverified += 1
        results[key] = r

    # 4) unexpected candidate directories (cross-run contamination)
    known = {ident for (_, ident) in expected.values()}
    for p in sorted(songs.glob("wsb_*")):
        if not p.is_dir():
            continue  # per-candidate .wav exports are expected byproducts
        if p.name not in known:
            problems.append(f"unexpected candidate directory: {p.name} (not in this run's "
                            f"evaluation_inputs)")

    # 5) classification summary (recovered finalize failures are classified,
    #    not problems -- immutable artifacts rule)
    classification["verified"] = len(results)
    classification["finalized"] = sum(1 for (_, ident) in expected.values()
                                      if (songs / ident / "result.json").is_file())
    classification["generated"] = len(journal) or len(expected)
    for ident, status in journal.items():
        if status == "finalize_failed" and (songs / ident / "result.json").is_file():
            classification["driver:finalize_failed (recovered)"] += 1

    truncated = sum(1 for r in results.values() if r.get("truncated"))
    complete = len(results)
    if args.mode == "full":
        verdict = "FULL" if (complete == 384 and not problems
                             and len(expected) == 384) else "PARTIAL"
    else:
        verdict = "PILOT" if (complete == len(expected) and expected and not problems) else "PILOT-INCOMPLETE"

    report = {
        "run": str(args.runs),
        "mode": args.mode,
        "dataset_revision_ok": dataset_ok,
        "expected_candidates": 384 if args.mode == "full" else len(expected),
        "expected_prompt_indices": len({i for (i, _) in expected}),
        "verified_complete": complete,
        "missing_or_invalid": (384 if args.mode == "full" else len(expected)) - complete,
        "truncated_but_complete": truncated,
        "unique_prompt_coverage": len({k[0] for k in results}),
        "identity_reverified": identity_reverified,
        "classification": dict(classification),
        "problem_count": len(problems),
        "problems": problems,
        "verdict": verdict,
    }
    print(json.dumps({k: v for k, v in report.items() if k != "problems"}, indent=2))
    if problems:
        print(f"problems ({len(problems)}):")
        for p in problems:
            print(" -", p)
    (args.runs / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if verdict in ("FULL", "PILOT") else 1


if __name__ == "__main__":
    raise SystemExit(main())
