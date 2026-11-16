#!/usr/bin/env python3
"""per_tail_analysis.py — P6.2 mathematically-consistent PER tail decomposition.

Fixes the denominator errors common in tail analyses:
  * selected-192 vs unselected-384 populations are NEVER compared directly;
    each statistic declares its population;
  * micro PER = total edits / total reference phonemes WITHIN that population;
  * capped / empty / truncated categories are handled overlap-aware (a
    candidate can be both capped and empty; double counting is excluded);
  * contribution of a subgroup to the aggregate = subgroup_edits / population
    phonemes (sums to the aggregate exactly, no residual gaps);
  * bootstrap CIs (candidate-level resampling within population).

Input: per_song.jsonl (384 rows, frozen evaluator schema)
Output: JSON analysis + human-readable summary.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path


def load_rows(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def per_fields(r):
    m = r.get("metrics", {}).get("per", {})
    return {
        "per": m.get("per"),
        "edits": m.get("edits"),
        "phonemes": m.get("reference_phonemes"),
        "truncated": bool(m.get("truncated")),
        "empty": (m.get("per") == 1.0 and (m.get("edits") or 0) > 0
                  and (m.get("reference_phonemes") or 0) > 0
                  and m.get("edits") == m.get("reference_phonemes")),
        # ASR-capped = transcript hit max_new_tokens (chars unreadable marker):
        "asr_truncated": bool(m.get("selected_asr_truncated")),
        "lang": r.get("lang"),
    }


def micro(rows, fields):
    edits = sum(f["edits"] or 0 for f in fields)
    phon = sum(f["phonemes"] or 0 for f in fields)
    return (edits / phon if phon else None), edits, phon


def bootstrap_ci(rows, n=2000, seed=0):
    rng = random.Random(seed)
    vals = []
    fields = [per_fields(r) for r in rows]
    for _ in range(n):
        sample = rng.choices(rows, k=len(rows))
        m, _, _ = micro(sample, [per_fields(r) for r in sample])
        if m is not None:
            vals.append(m)
    vals.sort()

    def pct(p):
        return vals[int(p * (len(vals) - 1))] if vals else None
    return pct(0.025), pct(0.975)


def analyze(path: Path) -> dict:
    rows = load_rows(path)
    assert len(rows) == 384, f"expected 384 candidates, got {len(rows)}"
    fields = [per_fields(r) for r in rows]
    # selection: evaluator picks lower-PER candidate per (prompt_index)
    by_prompt = {}
    for r, f in zip(rows, fields):
        k = r["prompt_index"]
        if k not in by_prompt or (f["per"] or 1) < (by_prompt[k][1]["per"] or 1):
            by_prompt[k] = (r, f)
    sel_rows = [r for r, _ in by_prompt.values()]
    sel_fields = [f for _, f in by_prompt.values()]
    unsel = [(r, f) for r, f in zip(rows, fields)
             if id(r) not in {id(x[0]) for x in by_prompt.values()}]

    def subgroup(pop_rows, pop_fields, pred):
        idx = [i for i, f in enumerate(pop_fields) if pred(f)]
        return [pop_rows[i] for i in idx], [pop_fields[i] for i in idx]

    out = {"source": str(path), "rows": len(rows),
           "populations": {}}
    for name, (prows, pfields) in {
            "selected_192": (sel_rows, sel_fields),
            "unselected_192": ([r for r, _ in unsel], [f for _, f in unsel]),
            "all_384": (rows, fields)}.items():
        m, e, p = micro(prows, pfields)
        pop = {"micro_per": round(m, 6) if m else None,
               "edits": e, "phonemes": p, "candidates": len(prows)}
        lo, hi = bootstrap_ci(prows) if len(prows) == 192 else (None, None)
        pop["ci95"] = [round(lo, 4) if lo else None, round(hi, 4) if hi else None]
        out["populations"][name] = pop

    sel = out["populations"]["selected_192"]
    total_edits, total_phon = sel["edits"], sel["phonemes"]

    cats = {
        "asr_capped": lambda f: f["asr_truncated"],
        "empty_transcript": lambda f: f["empty"],
        "capped_nonempty": lambda f: f["asr_truncated"] and not f["empty"],
        "uncapped": lambda f: not f["asr_truncated"],
        "per_gt_30pct": lambda f: (f["per"] or 0) > 0.30,
    }
    out["selected_subgroups_overlap_aware"] = {}
    for cname, pred in cats.items():
        srows, sfields = subgroup(sel_rows, sel_fields, pred)
        m, e, p = micro(srows, sfields)
        out["selected_subgroups_overlap_aware"][cname] = {
            "candidates": len(srows),
            "micro_per_within": round(m, 6) if m is not None else None,
            "edits": e, "phonemes": p,
            # contribution to the selected-192 aggregate (sums exactly):
            "edit_share_of_selected": round(e / total_edits, 4) if total_edits else None,
            "per_point_contribution": round(e / total_phon, 6) if total_phon else None,
        }
    # cross-tab capped x empty (excludes double counting explicitly)
    ct = Counter()
    for f in sel_fields:
        ct[(f["asr_truncated"], f["empty"])] += 1
    out["selected_crosstab_capped_empty"] = {
        f"capped={c},empty={e}": n for (c, e), n in sorted(ct.items())}
    # language split (selected)
    for lang in sorted({f["lang"] for f in sel_fields if f["lang"]}):
        srows, sfields = subgroup(sel_rows, sel_fields, lambda f, l=lang: f["lang"] == l)
        m, e, p = micro(srows, sfields)
        out["populations"][f"selected_{lang}"] = {
            "candidates": len(srows), "micro_per": round(m, 6),
            "edits": e, "phonemes": p}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("per_song_jsonl", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    res = analyze(args.per_song_jsonl)
    text = json.dumps(res, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
