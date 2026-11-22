#!/usr/bin/env python3
"""per_cross_arm_analysis.py — controlled PER decomposition across arms (M3.3).

Inputs are per-candidate official-evaluator receipts (per_song.jsonl). No raw
audio or text leaves the local host; outputs contain aggregates only.

Analyses:
  1. selected-192 recomputation with the official selection rule (min per,
     then edits, then |hyp-ref| phonemes, then repeat index) — never trusts
     a precomputed flag.
  2. selected-192 tail decomposition with EXACT denominators and overlap
     memberships (capped / uncapped / empty / per==1.0), per arm.
  3. paired per-prompt comparison across arms (same frozen prompts+seeds):
     Pearson/Spearman correlation of per-prompt micro PER, mean paired
     difference, bootstrap CI over prompts.
  4. ASR repeat determinism: whether the 4 ASR passes agree per candidate.
  5. prompt-level bootstrap CIs for every reported aggregate.

Statistical rules (mission M3): prompt is ALWAYS the resampling unit;
overlapping groups are reported with explicit memberships, never summed.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path


def load_rows(path: str | Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def sel_key(r: dict):
    """Exact mirror of the official frozen selection key (wsb_eval.py
    select_candidates): (per, edits, |len(phonemes of the SELECTED asr repeat)
    - reference_phonemes|, candidate_index), minimized per prompt.

    RC4 M4.2: the previous key summed phonemes over ALL asr_repeats and used
    selected_asr_repeat as the final component — it diverged from the official
    selection exactly at prompt 19 of armB_full_20261119T015756Z (PER and edits
    tie; official third component 3 (r1) vs 11 (r0)). See
    reports/w7900_rc4/04_SELECTION_TIE_REVIEW.md.
    """
    m = r["metrics"]["per"]
    rep = m["asr_repeats"][m["selected_asr_repeat"]]
    return (m.get("per", 1.0), m.get("edits", 10**9),
            abs(len(rep["phonemes"]) - m.get("reference_phonemes", 0)),
            r["candidate_index"])


def group_rows(rows: list[dict]) -> dict:
    g = defaultdict(list)
    for r in rows:
        g[r["prompt_index"]].append(r)
    return g


def micro(per_list, phon_list):
    tot = sum(phon_list)
    return (sum(e for e, p in zip(per_list, phon_list)) / tot) if tot else None


def per_prompt_micros(rows: list[dict]) -> dict[int, float]:
    """Unselected per-prompt micro PER (all candidates of the prompt)."""
    g = group_rows(rows)
    out = {}
    for p, rs in g.items():
        num = sum(x["metrics"]["per"]["edits"] for x in rs)
        den = sum(x["metrics"]["per"]["reference_phonemes"] for x in rs)
        out[p] = num / den if den else float("nan")
    return out


def select_192(rows: list[dict]) -> list[dict]:
    g = group_rows(rows)
    chosen = []
    for p in sorted(g):
        cands = sorted(g[p], key=sel_key)
        chosen.append(cands[0])
    return chosen


def bootstrap_ci(values, weights, n=10000, seed=7, alpha=0.05):
    """Prompt-level bootstrap of a weighted mean."""
    rng = random.Random(seed)
    idx = list(range(len(values)))
    stats = []
    for _ in range(n):
        samp = rng.choices(idx, k=len(idx))
        num = sum(values[i] * weights[i] for i in samp)
        den = sum(weights[i] for i in samp)
        stats.append(num / den if den else float("nan"))
    stats.sort()
    return stats[int(alpha / 2 * n)], stats[int((1 - alpha / 2) * n)]


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx = math.sqrt(sum((a - mx) ** 2 for a in x))
    vy = math.sqrt(sum((b - my) ** 2 for b in y))
    return cov / (vx * vy) if vx and vy else float("nan")


def spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk
    return pearson(ranks(x), ranks(y))


def repeats_identical(r: dict) -> bool | None:
    reps = r["metrics"]["per"].get("asr_repeats") or []
    texts = [x.get("text") for x in reps]
    if len(texts) < 2 or any(t is None for t in texts):
        return None
    return len(set(texts)) == 1


def analyze(name: str, rows: list[dict], out: dict):
    sel = select_192(rows)
    per = [r["metrics"]["per"] for r in sel]
    per_u = [r["metrics"]["per"] for r in rows]

    def stats_of(metrics, rows_):
        vals = [m["per"] for m in metrics]
        wts = [m["reference_phonemes"] for m in metrics]
        lo, hi = bootstrap_ci(vals, wts)
        return {"micro": sum(v * w for v, w in zip(vals, wts)) / sum(wts),
                "ci95": [lo, hi], "n": len(vals)}

    capped = [m for m in per if m.get("selected_asr_truncated")]
    uncapped = [m for m in per if not m.get("selected_asr_truncated")]
    ones = [m for m in per if m.get("per", 0) >= 0.999]
    empty = [m for r, m in zip(sel, per)
             if not any((x.get("text") or "").strip()
                        for x in m.get("asr_repeats", []))]
    det = [repeats_identical(r) for r in rows]
    out[name] = {
        "selected_192": stats_of(per, sel),
        "unselected_384": stats_of(per_u, rows),
        "selected_capped": stats_of(capped, sel),
        "selected_uncapped": stats_of(uncapped, sel),
        "selected_per_eq_1": {"n": len(ones),
                              "edits_share_of_selected": (
                                  sum(m["edits"] for m in ones) /
                                  sum(m["edits"] for m in per)) if per else None},
        "selected_empty_transcript": {"n": len(empty)},
        "memberships": {
            "capped_and_per1": sum(1 for m in per if m.get(
                "selected_asr_truncated") and m.get("per", 0) >= 0.999),
            "capped_and_empty": sum(
                1 for m, e in zip(per, empty) if e and m.get(
                    "selected_asr_truncated")) if len(empty) == len(per) else None,
            "note": "groups overlap; contributions must not be summed",
        },
        "asr_repeat_determinism": {
            "candidates_with_repeats": sum(1 for d in det if d is not None),
            "all_repeats_identical": sum(1 for d in det if d is True),
        },
        "by_lang": {},
        "selected_gt_30pct": sum(1 for m in per if m.get("per", 0) > 0.30),
        "unselected_capped_of_384": sum(
            1 for m in per_u if m.get("selected_asr_truncated")),
    }
    for lang in {r["lang"] for r in sel}:
        sub = [r["metrics"]["per"] for r in sel if r["lang"] == lang]
        out[name]["by_lang"][lang] = stats_of(sub, sel)
    # per-prompt unselected micros for pairing
    out[name + "__perprompt"] = per_prompt_micros(rows)
    return out[name]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--armA", required=True, help="fresh Arm A per_song.jsonl")
    ap.add_argument("--armC", default=None,
                    help="second arm per_song.jsonl (e.g. gfx1151 SGLang)")
    ap.add_argument("--armC-name", default="gfx1151")
    ap.add_argument("--out", required=True, help="output JSON")
    args = ap.parse_args()

    out: dict = {}
    a_rows = load_rows(args.armA)
    analyze("armA_fresh", a_rows, out)
    c_rows = None
    if args.armC:
        c_rows = load_rows(args.armC)
        analyze(args.armC_name, c_rows, out)

    if c_rows is not None:
        a_pp = out.pop("armA_fresh__perprompt")
        c_pp = out.pop(args.armC_name + "__perprompt")
        common = sorted(set(a_pp) & set(c_pp))
        x = [a_pp[p] for p in common]
        y = [c_pp[p] for p in common]
        diffs = [b - a for a, b in zip(x, y)]
        lo, hi = bootstrap_ci(diffs, [1] * len(diffs))
        out["paired_per_prompt"] = {
            "unit": "prompt (unselected, both candidates, official frozen seeds)",
            "n_prompts": len(common),
            "pearson_r": pearson(x, y),
            "spearman_rho": spearman(x, y),
            "mean_paired_difference": sum(diffs) / len(diffs),
            "diff_ci95": [lo, hi],
            "interpretation": "high correlation => shared prompt-structural "
                              "difficulty; the systematic offset vs the official "
                              "baseline is then common-mode (generation numerics "
                              "and/or evaluator backend), not arm-specific",
        }
    else:
        out.pop("armA_fresh__perprompt", None)

    Path(args.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items()
                      if not isinstance(v, dict) or "micro" in str(v)[:200]},
                     indent=1)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
