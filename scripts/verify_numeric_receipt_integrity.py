#!/usr/bin/env python3
"""verify_numeric_receipt_integrity.py — C1 P1.3.

Proves the security redaction (raw text -> numeric receipts) did NOT alter
scientific evidence. For every candidate row present in BOTH the original
(pre-redaction) file and the public numeric file:

  * candidate identity fields (id, prompt_index, candidate_index, seed,
    sample_id/clip_id, audio hashes, model identities) are IDENTICAL
  * every NUMERIC leaf under metrics is bit-identical (float equality on the
    stored value)
  * row/candidate counts match (no silent drops)
  * aggregate summary numbers match where present

Fail-closed on missing ids, count drift, or numeric drift. Never prints
text-bearing field values.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

IDENTITY_KEYS = ["id", "prompt_index", "candidate_index", "seed",
                 "sample_id", "clip_id", "lang", "cot", "result_sha256",
                 "audio_sha256", "decoder_identity", "generator_identity",
                 "generation_identity", "status", "generation_truncated",
                 "generation_condition", "generation_scope", "control_lang"]
TEXT_KEYS = {"target", "reference_lyrics", "reference_tokens",
             "control_prompt", "tags_full", "style_target", "genre_raw",
             "title", "source", "text", "raw_chunks", "phonemes",
             "lyrics", "transcript", "reference_phonemes_list"}


def numeric_leaves(obj, loc=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in TEXT_KEYS:
                continue
            yield from numeric_leaves(v, f"{loc}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from numeric_leaves(v, f"{loc}[{i}]")
    elif isinstance(obj, bool):
        yield loc, obj
    elif isinstance(obj, (int, float)):
        yield loc, obj


def load_jsonl_ref(ref: str, name: str):
    out = subprocess.run(["git", "show", f"{ref}:{name}"], cwd=ROOT,
                         capture_output=True)
    if out.returncode != 0:
        return None
    return [json.loads(l) for l in out.stdout.decode().splitlines()
            if l.strip()]


def compare_pairs(orig_rows, new_rows, label):
    """Fail-closed on duplicate IDs, added/dropped rows and any metric drift."""
    problems = []
    for side, rows in (("original", orig_rows), ("public", new_rows)):
        ids = [r.get("id") for r in rows if isinstance(r, dict)]
        if len(ids) != len(rows) or any(not isinstance(i, str) or not i for i in ids):
            problems.append(f"{label}: invalid {side} row/ID schema")
        if len(ids) != len(set(ids)):
            problems.append(f"{label}: duplicate {side} candidate ID")
    if problems:
        return problems

    original = {row["id"]: row for row in orig_rows}
    public = {row["id"]: row for row in new_rows}
    if len(orig_rows) != len(new_rows):
        problems.append(f"{label}: row count {len(orig_rows)} -> {len(new_rows)}")
    missing, added = set(original) - set(public), set(public) - set(original)
    if missing:
        problems.append(f"{label}: {len(missing)} IDs dropped")
    if added:
        problems.append(f"{label}: {len(added)} unexpected IDs added")
    for cid in sorted(set(original) & set(public)):
        old, new = original[cid], public[cid]
        for key in IDENTITY_KEYS:
            if key in old and old[key] != new.get(key):
                problems.append(f"{label}[{cid}]: identity {key} changed/missing")
            if key not in old and key in new:
                problems.append(f"{label}[{cid}]: unexpected identity {key} added")
        a = dict(numeric_leaves(old.get("metrics", {})))
        b = dict(numeric_leaves(new.get("metrics", {})))
        problems += numeric_difference(a, b, f"{label}[{cid}].metrics")
    return problems


def numeric_difference(original, public, label):
    """All expected numeric paths must survive, including ASR repeat counters."""
    problems = []
    removed = set(original) - set(public)
    added = set(public) - set(original)
    for path in sorted(removed):
        problems.append(f"{label}: numeric dropped {path}")
    for path in sorted(added):
        problems.append(f"{label}: numeric added {path}")
    for path in sorted(set(original) & set(public)):
        if original[path] != public[path] or type(original[path]) is not type(public[path]):
            problems.append(f"{label}: numeric changed {path}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig-ref", default="8c242ba",
                    help="pre-redaction commit carrying the original receipts "
                         "(8c242ba = verified PR #9 head before PR #10's redaction)")
    ap.add_argument("--new-ref", default="HEAD")
    args = ap.parse_args()
    # fail-closed: the comparison ref must EXIST (a typo'd ref must not
    # degrade into a vacuous PASS)
    exists = subprocess.run(["git", "rev-parse", "--verify",
                             "--quiet", f"{args.orig_ref}^{{commit}}"],
                            cwd=ROOT, capture_output=True)
    if exists.returncode != 0:
        print(f"::error::--orig-ref {args.orig_ref} is not a valid commit — "
              f"refusing to issue a vacuous PASS", file=sys.stderr)
        return 2
    pairs = [
        "evidence/evaluator_audit/per_runA_2candidates.jsonl",
        "evidence/evaluator_audit/per_runB_10candidates.jsonl",
        "evidence/evaluator_audit/per_runC_10candidates_repeat.jsonl",
        "evidence/publication/armA_pilot/per_song.jsonl",
    ]
    problems = []
    for name in pairs:
        orig = load_jsonl_ref(args.orig_ref, name)
        new = load_jsonl_ref(args.new_ref, name)
        if orig is None:
            problems.append(f"{name}: original receipt missing at {args.orig_ref}")
            continue
        if new is None:
            problems.append(f"{name}: MISSING at {args.new_ref} "
                            f"(numeric receipt must exist)")
            continue
        problems += compare_pairs(orig, new, name)
        print(f"compared {name}: {len(orig)} -> {len(new)} rows")

    # scoring_snapshot.json: aggregates must match numerically
    def snap(ref):
        out = subprocess.run(["git", "show", f"{ref}:evidence/gfx1100/"
                                f"scoring_snapshot.json"], cwd=ROOT,
                             capture_output=True)
        if out.returncode != 0:
            return None
        d = json.loads(out.stdout)
        return dict(numeric_leaves(d))

    o, n = snap(args.orig_ref), snap(args.new_ref)
    if o is None or n is None:
        problems.append("scoring_snapshot.json: missing original or public snapshot")
    else:
        diffs = numeric_difference(o, n, "scoring_snapshot.json")
        problems.extend(diffs)
        print(f"compared scoring_snapshot.json: {len(o)} original and {len(n)} "
              f"public numeric leaves, {len(diffs)} discrepancies")

    if problems:
        for p in problems[:80]:
            print("::error::" + p, file=sys.stderr)
        print(f"FAIL: {len(problems)} integrity problems", file=sys.stderr)
        return 1
    print("PASS: numeric evidence identical between original and public "
          "numeric receipts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
