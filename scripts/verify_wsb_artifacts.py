#!/usr/bin/env python3
"""verify_wsb_artifacts.py v2 - strict WSB run auditor (gfx1100/gfx1151 portable).

Fixes over v1 (mission Phase 6 hardening):
  - FULL MODE CAN NO LONGER SILENTLY REDUCE ITS EXPECTED COUNT. `--mode full`
    (default) requires exactly 384 verified candidates, 192 unique prompts,
    exactly candidates {0,1} per prompt. `--expect` is cross-checked, never
    used to lower the bar.
  - NO ERROR-LIST RESET: every problem accumulates from the start (v1 built
    `problems` then overwrote it with `[]`, swallowing seed mismatches).
  - Detects: missing candidates, wrong seeds vs the frozen manifest, duplicate
    candidate identities, duplicate directories, UNEXPECTED candidate dirs,
    failed official verify_result, request deviations (seed/cot/cfg), wrong
    dataset revision (manifest row hash), truncated-but-valid (allowed,
    counted).
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

WS = Path(os.environ.get("YUE2_WORKSPACE",
                         Path(__file__).resolve().parents[2]))
MANIFEST_PATH = WS / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
MANIFEST_SHA256 = "859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0"

sys.path.insert(0, str(WS / "benchmark" / "wsb_metrics"))
from artifact_storage import verify_result  # official frozen checker  # noqa: E402


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--mode", choices=("full", "pilot"), default="full")
    ap.add_argument("--expect", type=int, default=384,
                    help="full mode: must equal 384; pilot: subset size (informational)")
    ap.add_argument("--allow-missing-dataset-hash", action="store_true",
                    help="record (not ignore) a manifest hash mismatch instead of failing")
    args = ap.parse_args()

    problems: list[str] = []          # NEVER reset after starting
    results: dict[tuple[int, int], dict] = {}

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
            problems.append(f"evaluation_inputs: duplicate entry for {pair} ({n}x)")

    if args.mode == "full":
        if args.expect != 384:
            problems.append(f"full mode requires --expect 384, got {args.expect}")
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
        for i in prompts:
            js = sorted(j for (ii, j) in expected if ii == i)
            if js != [0, 1]:
                problems.append(f"prompt {i}: candidates {js} != [0, 1]")

    # 2) per-candidate official verification
    songs = args.runs / "songs"
    if not songs.is_dir():
        print(f"FATAL: {songs} missing")
        return 2
    for key, (seed, ident) in sorted(expected.items()):
        cand = songs / ident
        if not (cand / "result.json").is_file():
            problems.append(f"{ident}: missing result.json")
            continue
        try:
            r = verify_result(cand)
        except Exception as exc:
            problems.append(f"{ident}: official verify_result FAILED: "
                            f"{type(exc).__name__}: {exc}")
            continue
        req_path = cand / "request.json"
        if not req_path.is_file():
            problems.append(f"{ident}: missing request.json")
            continue
        req = json.loads(req_path.read_text())
        if req.get("seed") != seed:
            problems.append(f"{ident}: request seed {req.get('seed')} != {seed}")
        if req.get("cot") != "full":
            problems.append(f"{ident}: request cot {req.get('cot')!r} != 'full'")
        if req.get("cfg_scale") not in (1.0, None):
            problems.append(f"{ident}: request cfg_scale {req.get('cfg_scale')} not 1.0/None")
        results[key] = r

    # 3) unexpected candidate directories (cross-run contamination)
    known = {ident for (_, ident) in expected.values()}
    for p in sorted(songs.glob("wsb_*")):
        if not p.is_dir():
            continue  # per-candidate .wav exports are expected byproducts
        if p.name not in known:
            problems.append(f"unexpected candidate dir: {p.name} (not in this run's "
                            f"evaluation_inputs)")

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
        "verified_complete": complete,
        "missing_or_invalid": (384 if args.mode == "full" else len(expected)) - complete,
        "truncated_but_complete": truncated,
        "unique_prompt_coverage": len({k[0] for k in results}),
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
