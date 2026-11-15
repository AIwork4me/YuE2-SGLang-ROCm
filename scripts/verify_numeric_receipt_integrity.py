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
             "title", "source", "text", "raw_chunks", "asr_repeats",
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
    problems = []
    o = {r["id"]: r for r in orig_rows}
    n = {r["id"]: r for r in new_rows}
    if len(orig_rows) != len(new_rows):
        problems.append(f"{label}: row count {len(orig_rows)} -> {len(new_rows)}")
    missing = set(o) - set(n)
    if missing:
        problems.append(f"{label}: {len(missing)} ids dropped (e.g. {sorted(missing)[0]})")
    for cid in sorted(set(o) & set(n)):
        for k in IDENTITY_KEYS:
            if k in o[cid] and o[cid][k] != n[cid].get(k):
                problems.append(f"{label}[{cid}]: identity {k} changed")
        onum = dict(numeric_leaves(o[cid].get("metrics", {})))
        nnum = dict(numeric_leaves(n[cid].get("metrics", {})))
        for loc in sorted(set(onum) | set(nnum)):
            if loc not in nnum:
                problems.append(f"{label}[{cid}]: numeric dropped {loc}")
            elif loc not in onum:
                problems.append(f"{label}[{cid}]: numeric added {loc}")
            elif onum[loc] != nnum[loc]:
                problems.append(f"{label}[{cid}]: numeric changed {loc}: "
                                f"{onum[loc]} -> {nnum[loc]}")
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
            print(f"SKIP {name}: absent at {args.orig_ref}")
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
    if o is not None and n is not None:
        # compare only keys present in both (the redacted snapshot may add
        # receipt hashes); any changed numeric value is a violation
        common = set(o) & set(n)
        drift = [k for k in sorted(common) if o[k] != n[k]]
        for k in drift:
            problems.append(f"scoring_snapshot.json: numeric changed {k}: "
                            f"{o[k]} -> {n[k]}")
        print(f"compared scoring_snapshot.json: {len(common)} shared numeric "
              f"leaves, {len(drift)} drifted")

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
