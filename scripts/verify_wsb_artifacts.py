#!/usr/bin/env python3
"""Audit a WSB run directory against the frozen WildSongBench protocol.

Modes
-----
full   (default) The complete official benchmark: exactly the 384 unique
       candidates implied by the frozen manifest (192 prompt indices x 2
       candidates each). A 10-candidate subset can NEVER pass full mode:
       missing candidates, missing prompt indices and any identity problems
       are all reported as failures. --expect is not consulted (and is
       rejected) in full mode; 384 is implied by the frozen protocol.
subset An explicitly scoped pilot/diagnostic run. The expected set is read
       from the run's own evaluation_inputs.jsonl; --expect must EQUAL the
       number of selected rows exactly -- it is never adjusted silently.

For every expected candidate the audit verifies, in order:
  1. presence of result.json (finalized)
  2. the official frozen artifact check (wsb_metrics artifact_storage.
     verify_result: hashes of audio.flac / npy / json files, status complete)
  3. the frozen request contract: seed == the official seed formula
     (831001+i / 831019+i), cot == full, cfg_scale == 1.0, and style/lyrics
     byte-equal to the frozen manifest row
  4. run identity: sha256 identity({request, config, weights}) recomputed
     from the bundle equals result.json.identity
Any candidate directory under songs/ that is NOT in the expected set is an
"unexpected identity" failure (stale or mixed-run artifacts are rejected,
never silently ignored).

Exit code 0 only for verdict FULL: every expected candidate verified, zero
problems. The classification (generated / finalized / verified / failed /
truncated / pending) is emitted for monitoring and never weakens the gate.

Usage:
  python verify_wsb_artifacts.py --runs runs/wsb_full                    # full 384
  python verify_wsb_artifacts.py --runs runs/wsb_pilot --mode subset --expect 10
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

WS = Path(os.environ.get("WS", "/home/amd/Desktop/YuE2"))
sys.path.insert(0, str(WS / "benchmark" / "WildSongBench" / "wsb_metrics"))

from artifact_storage import verify_result  # official frozen checker

MANIFEST_PATH = WS / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
FULL_EXPECTED_CANDIDATES = 384
FULL_PROMPTS = 192
CANDIDATES_PER_PROMPT = 2
BASE_SEEDS = (831001, 831019)


def load_manifest(path: Path = MANIFEST_PATH) -> list[dict]:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    if len(rows) != FULL_PROMPTS or [r["prompt_index"] for r in rows] != list(range(FULL_PROMPTS)):
        raise SystemExit(f"frozen manifest is not the official 192-row file: {path}")
    return rows


def expected_from_manifest(rows: list[dict]) -> dict[tuple[int, int], dict]:
    """The full official expected set: 192 prompts x 2 candidates, official seeds."""
    out = {}
    for row in rows:
        i = row["prompt_index"]
        seeds = row["candidate_ar_seeds"]
        if seeds[:CANDIDATES_PER_PROMPT] != [b + i for b in BASE_SEEDS]:
            raise SystemExit(f"frozen manifest seed formula violated at prompt {i}")
        for j, seed in enumerate(seeds[:CANDIDATES_PER_PROMPT]):
            out[(i, j)] = {"seed": seed, "ident": f"wsb_{i:03d}_r{j}_s{seed}", "row": row}
    if len(out) != FULL_EXPECTED_CANDIDATES:
        raise SystemExit("internal error building expected set")
    return out


def expected_from_selection(rows: list[dict], selected: list[dict]) -> dict[tuple[int, int], dict]:
    by_index = {r["prompt_index"]: r for r in rows}
    out = {}
    for entry in selected:
        i, j, seed = entry["prompt_index"], entry["candidate_index"], entry["seed"]
        if j not in range(CANDIDATES_PER_PROMPT):
            raise SystemExit(f"subset selection has invalid candidate_index {j} at prompt {i}")
        if seed != BASE_SEEDS[j] + i:
            raise SystemExit(f"subset selection seed {seed} violates the official formula at prompt {i}")
        out[(i, j)] = {"seed": seed, "ident": f"wsb_{i:03d}_r{j}_s{seed}", "row": by_index[i]}
    return out


def canonical_identity(request: dict, config: dict, weights: dict) -> str:
    blob = json.dumps({"request": request, "config": config, "weights": weights},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def audit(runs: Path, expected: dict[tuple[int, int], dict], mode: str) -> dict:
    problems: list[str] = []
    songs = runs / "songs"
    classification = Counter()
    verified, truncated, identities_ok = 0, 0, 0

    expected_idents = {e["ident"] for e in expected.values()}
    # Candidate bundles are DIRECTORIES. The driver deliberately keeps each
    # candidate's raw WAV (wsb_*.wav) next to its bundle as an immutable
    # artifact; files are never candidate identities.
    present = {p.name: p for p in songs.glob("wsb_*") if p.is_dir()} if songs.is_dir() else {}
    for name in sorted(set(present) - expected_idents):
        problems.append(f"unexpected candidate directory: {name} (stale or mixed-run artifact)")
    # Duplicate identity: a directory claiming the same (prompt, candidate)
    # slot as an expected candidate but under a different name/seed.
    import re

    for name in sorted(present):
        m = re.fullmatch(r"wsb_(\d+)_r(\d+)_s(\d+)", name)
        if not m:
            problems.append(f"unparsable candidate directory name: {name}")
            continue
        key = (int(m.group(1)), int(m.group(2)))
        if key in expected and name != expected[key]["ident"]:
            problems.append(
                f"duplicate identity for prompt {key[0]} candidate {key[1]}: "
                f"{name} conflicts with expected {expected[key]['ident']}")

    for (i, j), exp in sorted(expected.items()):
        ident = exp["ident"]
        cand = songs / ident
        if not cand.is_dir():
            classification["pending"] += 1
            problems.append(f"{ident}: missing (no candidate directory)")
            continue
        classification["generated"] += 1
        result_path = cand / "result.json"
        if not result_path.is_file():
            classification["generated (not finalized)"] += 1
            problems.append(f"{ident}: not finalized (missing result.json)")
            continue
        classification["finalized"] += 1
        try:
            result = verify_result(cand)  # official: artifact hashes + status complete
        except Exception as exc:
            problems.append(f"{ident}: artifact integrity FAILED: {type(exc).__name__}: {exc}")
            continue
        classification["verified"] += 1
        verified += 1
        if result.get("truncated"):
            truncated += 1

        request = json.loads((cand / "request.json").read_text())
        # Frozen protocol checks (all errors collected, never first-only)
        if request.get("seed") != exp["seed"]:
            problems.append(f"{ident}: seed {request.get('seed')} != official {exp['seed']}")
        if request.get("cot") != "full":
            problems.append(f"{ident}: cot {request.get('cot')!r} != 'full'")
        if request.get("cfg_scale") != 1.0:
            problems.append(f"{ident}: cfg_scale {request.get('cfg_scale')!r} != 1.0")
        if request.get("style") != exp["row"]["style"] or request.get("lyrics") != exp["row"]["lyrics"]:
            problems.append(f"{ident}: style/lyrics differ from frozen manifest row")
        # Run identity: recompute identity({request, config, weights})
        try:
            config = json.loads((cand / "config.json").read_text())
            weights = result.get("weights", {})
            recomputed = canonical_identity(request, config, weights)
            if recomputed != result.get("identity"):
                problems.append(f"{ident}: result.json identity != recomputed identity(request,config,weights)")
            else:
                identities_ok += 1
        except Exception as exc:
            problems.append(f"{ident}: identity recompute failed: {exc}")

    # Driver-side failures (from generation_manifest.jsonl), reported alongside.
    # A failure record whose candidate NOW verifies complete on disk documents
    # a recovered incident (e.g. re-finalization), not an open defect: the
    # immutable artifacts are authoritative over driver bookkeeping.
    driver = runs / "generation_manifest.jsonl"
    if driver.is_file():
        for line in driver.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            status = str(rec.get("status", ""))
            if status.startswith("complete"):
                continue
            cand = songs / str(rec.get("id", ""))
            if cand.is_dir() and (cand / "result.json").is_file():
                try:
                    verify_result(cand)
                    classification[f"driver:{status} (recovered)"] += 1
                    continue
                except Exception:
                    pass
            classification[f"driver:{status}"] += 1
            problems.append(f"{rec.get('id')}: driver status {status!r} ({str(rec.get('error', ''))[:120]})")

    return {
        "run": str(runs),
        "mode": mode,
        "expected_candidates": len(expected),
        "expected_prompt_indices": len({k[0] for k in expected}),
        "verified_complete": verified,
        "identity_reverified": identities_ok,
        "truncated_but_complete": truncated,
        "classification": dict(classification),
        "problems": problems,
        "verdict": "FULL" if not problems and verified == len(expected) else "PARTIAL",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--mode", choices=("full", "subset"), default="full")
    ap.add_argument("--expect", type=int, default=None,
                    help="subset mode ONLY: must exactly equal the number of selected rows")
    args = ap.parse_args()

    rows = load_manifest()
    if args.mode == "full":
        if args.expect is not None:
            raise SystemExit("--expect is not valid in full mode; the frozen protocol implies 384")
        expected = expected_from_manifest(rows)
    else:
        if args.expect is None:
            raise SystemExit("subset mode requires an explicit --expect (the "
                             "declared scope of the pilot); full mode needs none")
        inputs_path = args.runs / "evaluation_inputs.jsonl"
        if not inputs_path.is_file():
            raise SystemExit(f"subset mode requires {inputs_path}")
        selected = [json.loads(l) for l in inputs_path.read_text().splitlines() if l.strip()]
        if args.expect != len(selected):
            raise SystemExit(f"--expect {args.expect} != {len(selected)} selected rows; "
                             "the expectation is never adjusted silently")
        keys = [(e["prompt_index"], e["candidate_index"]) for e in selected]
        if len(set(keys)) != len(keys):
            raise SystemExit("duplicate (prompt_index, candidate_index) rows in "
                             "evaluation_inputs.jsonl; refusing to collapse silently")
        expected = expected_from_selection(rows, selected)

    report = audit(args.runs, expected, args.mode)
    printable = dict(report)
    printable["problems"] = f"{len(report['problems'])} problem(s) (full list in audit.json)"
    print(json.dumps(printable, indent=2))
    if report["problems"]:
        print("problems:", file=sys.stderr)
        for p in report["problems"][:100]:
            print(" -", p, file=sys.stderr)
        if len(report["problems"]) > 100:
            print(f" ... and {len(report['problems']) - 100} more", file=sys.stderr)
    (args.runs / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["verdict"] == "FULL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
