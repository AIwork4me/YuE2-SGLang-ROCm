#!/usr/bin/env python3
"""rc5_selection_audit.py — RC5.1 P0.5.3 independent best-of-2 selection audit.

Recomputes the official WildSongBench selection from the per-song results
WITHOUT using the evaluator's own select_candidates(), then compares against
the evaluator's chosen candidates. The official ordering key (verbatim from
wsb_eval.py select_candidates) is, per prompt:

    min by (per, edits, abs(len(selected_repeat.phonemes) - reference_phonemes),
            candidate_index)

A simplified min(PER) is NOT used: the full tuple decides ties (the
historical prompt-19 tie-break bug was exactly a simplified-key error).

Usage:
  python3 scripts/rc5_selection_audit.py --per-song <out>/per_song.jsonl \
      --summary <out>/summary.json --run-dir <wsb_full> \
      --out reports/w7900_rc5/rc5_1/05_SELECTION_AUDIT.json
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path


def official_key(row):
    per = row["metrics"]["per"]
    repeat = per["asr_repeats"][per["selected_asr_repeat"]]
    return (per["per"], per["edits"],
            abs(len(repeat["phonemes"]) - per["reference_phonemes"]),
            row["candidate_index"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-song", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    rows = [json.loads(l) for l in a.per_song.read_text().splitlines() if l.strip()]
    summary = json.loads(a.summary.read_text())
    ev = {e["id"]: e for e in [json.loads(l) for l in
                               (a.run_dir / "journal.jsonl").read_text().splitlines() if l.strip()]
          if e.get("event") == "result" and e.get("status") == "complete"}

    problems = []
    if len(rows) != 384:
        problems.append(f"per_song rows = {len(rows)} != 384")
    ids = [r["id"] for r in rows]
    if len(set(ids)) != 384:
        problems.append("duplicate candidate ids in per_song")

    # independent selection with the FULL official key
    my_sel = {}
    for i in range(192):
        cands = [r for r in rows if r["prompt_index"] == i]
        if not cands:
            problems.append(f"prompt {i} missing")
            continue
        my_sel[i] = min(cands, key=official_key)

    # evaluator's selection
    ev_sel = {(r["prompt_index"], r["candidate_index"]): r for r in
              summary.get("selected_candidates", [])}

    # compare identities + audio hashes + PER values
    identity_match = audio_match = 0
    mismatches = []
    for i, mine in my_sel.items():
        ev_row = next((r for (pi, ci), r in ev_sel.items() if pi == i), None)
        if ev_row is None:
            mismatches.append(f"prompt {i}: evaluator selection missing")
            continue
        if ev_row["candidate_index"] != mine["candidate_index"]:
            ev_full = next(r for r in rows if r["prompt_index"] == i
                           and r["candidate_index"] == ev_row["candidate_index"])
            k_mine, k_ev = official_key(mine), official_key(ev_full)
            if k_ev < k_mine:
                mismatches.append(
                    f"prompt {i}: evaluator picked c{ev_row['candidate_index']} key={k_ev} "
                    f"but the independent minimum is c{mine['candidate_index']} key={k_mine}")
                continue
            # k_mine < k_ev cannot happen if the evaluator is right; equality
            # is impossible for distinct candidate_index. Record as inversion.
            mismatches.append(f"prompt {i}: selection differs (evaluator c{ev_row['candidate_index']})")
            continue
        if ev_row["audio_sha256"] == mine["audio_sha256"] and ev_row["seed"] == mine["seed"]:
            identity_match += 1
            audio_match += 1
        else:
            mismatches.append(f"prompt {i}: identity/audio hash mismatch")

    # selected/unselected PER aggregates (micro = per-phoneme-pool, macro = per-prompt mean)
    def per_of(r):
        return r["metrics"]["per"]["per"]

    selected_rows = list(my_sel.values())
    unselected_rows = [r for r in rows if r not in selected_rows]
    micro_sel = (sum(r["metrics"]["per"]["edits"] for r in selected_rows)
                 / sum(r["metrics"]["per"]["reference_phonemes"] for r in selected_rows))
    micro_unsel = (sum(r["metrics"]["per"]["edits"] for r in unselected_rows)
                   / sum(r["metrics"]["per"]["reference_phonemes"] for r in unselected_rows))
    macro_sel = sum(per_of(r) for r in selected_rows) / len(selected_rows)
    macro_unsel = sum(per_of(r) for r in unselected_rows) / len(unselected_rows)

    capped = sum(1 for r in rows if any(
        rr.get("truncated") for rr in r["metrics"]["per"]["asr_repeats"]))
    empty = sum(1 for r in rows if all(
        not (rr.get("text") or rr.get("transcript") or "").strip()
        for rr in r["metrics"]["per"]["asr_repeats"]))
    per_eq_1 = sum(1 for r in rows if per_of(r) >= 1.0 - 1e-12)

    report = {
        "schema": "yue2-rc5_1-selection-audit/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raw_candidate_coverage": f"{len(rows)}/384",
        "selected_prompt_coverage": f"{len(my_sel)}/192",
        "official_vs_independent_identity": f"{identity_match}/192",
        "selected_audio_hash_match": f"{audio_match}/192",
        "selection_key": "(per, edits, abs(len(phonemes)-reference), candidate_index) - full official tuple, verbatim",
        "mismatches": mismatches,
        "per": {
            "selected_micro": round(micro_sel, 6), "selected_macro": round(macro_sel, 6),
            "unselected_micro": round(micro_unsel, 6), "unselected_macro": round(macro_unsel, 6),
            "capped_candidate_count": capped,
            "empty_all_repeats_count": empty,
            "per_eq_1_count": per_eq_1,
            "note": "empty-vs-capped-vs-genuine high PER are distinguished, never conflated",
        },
        "problems": problems,
        "VERDICT": "PASS" if not problems and not mismatches and identity_match == 192
        else "FAIL",
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in (
        "raw_candidate_coverage", "selected_prompt_coverage",
        "official_vs_independent_identity", "VERDICT")}))
    return 0 if report["VERDICT"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
