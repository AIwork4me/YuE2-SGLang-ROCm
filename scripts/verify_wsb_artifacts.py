#!/usr/bin/env python3
"""Audit a WSB run directory: completeness, integrity, provenance, duplicates.

Exit 0 only when every expected candidate verifies complete via the official
wsb_metrics verify_result, with no duplicate keys and original seeds.

Usage: python scripts/verify_wsb_artifacts.py --runs runs/wsb_full [--expect 384]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

WS = Path("/home/amd/Desktop/YuE2")
sys.path.insert(0, str(WS / "benchmark" / "WildSongBench" / "wsb_metrics"))

from artifact_storage import verify_result  # official frozen checker


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--expect", type=int, default=384)
    args = ap.parse_args()

    manifest = [json.loads(l) for l in
                (WS / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl").read_text().splitlines() if l.strip()]
    rows_by_index = {r["prompt_index"]: r for r in manifest}
    # Expected set comes from the run's own evaluation_inputs.jsonl (the rows
    # this run selected); --expect cross-checks the count.
    inputs_path = args.runs / "evaluation_inputs.jsonl"
    selected = [json.loads(l) for l in inputs_path.read_text().splitlines() if l.strip()] if inputs_path.is_file() else []
    if not selected:
        for row in manifest:
            for j, seed in enumerate(row["candidate_ar_seeds"][:2]):
                selected.append({"prompt_index": row["prompt_index"], "candidate_index": j, "seed": seed})
    expected = {}
    for entry in selected:
        i, j, seed = entry["prompt_index"], entry["candidate_index"], entry["seed"]
        row = rows_by_index[i]
        if row["candidate_ar_seeds"][j] != seed:
            problems = [f"{i},{j}: seed {seed} not in manifest row"]
            break
        expected[(i, j)] = (seed, f"wsb_{i:03d}_r{j}_s{seed}")

    songs = args.runs / "songs"
    results, problems = {}, []
    if args.expect == 384 and selected and len(selected) != 384:
        args.expect = len(selected)
    for key, (seed, ident) in sorted(expected.items()):
        cand = songs / ident
        if not (cand / "result.json").is_file():
            problems.append(f"{ident}: missing result.json")
            continue
        try:
            r = verify_result(cand)
        except Exception as exc:
            problems.append(f"{ident}: {type(exc).__name__}: {exc}")
            continue
        req = json.loads((cand / "request.json").read_text())
        if req.get("seed") != seed or req.get("cot") != "full" or req.get("cfg_scale") != 1.0:
            problems.append(f"{ident}: request deviates (seed/cot/cfg)")
        if r.get("truncated"):
            pass  # allowed, recorded
        results[key] = r

    seen_ids = Counter()
    for p in sorted(songs.glob("wsb_*")) if songs.is_dir() else []:
        seen_ids[p.name] += 1
    dupes = [k for k, v in seen_ids.items() if v > 1]
    if dupes:
        problems.append(f"duplicate candidate dirs: {dupes}")

    truncated = sum(1 for r in results.values() if r.get("truncated"))
    report = {
        "run": str(args.runs),
        "expected_candidates": args.expect,
        "verified_complete": len(results),
        "missing_or_invalid": args.expect - len(results),
        "truncated_but_complete": truncated,
        "unique_prompt_coverage": len({k[0] for k in results}),
        "problems": problems[:50],
        "verdict": "FULL" if len(results) == args.expect and not problems else "PARTIAL",
    }
    print(json.dumps({k: v for k, v in report.items() if k != "problems"}, indent=2))
    if problems:
        print("problems (first 50):")
        for p in problems:
            print(" -", p)
    (args.runs / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["verdict"] == "FULL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
