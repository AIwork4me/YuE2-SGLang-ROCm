#!/usr/bin/env python3
"""summarize_campaign.py — deterministic campaign metric tables from raw receipts.

Reads the official evaluator outputs (scores/summary.json, additional/summary.json,
per_song.jsonl) and emits one machine-readable JSON + one Markdown table per
campaign. Never hand-transcribes numbers (mission 7.7).

Usage:
  python scripts/summarize_campaign.py --run <run_dir> --label "Arm B (SGLang)" \
      [--evidence-out evidence/publication/armB_campaign/]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def micro(rows):
    e = sum(r["metrics"]["per"]["edits"] for r in rows)
    n = sum(r["metrics"]["per"]["reference_phonemes"] for r in rows)
    return (e / n if n else float("nan")), e, n


def bootstrap_ci_micro(rows, n_boot=10000, seed=1234):
    """Bootstrap 95% CI over songs for the micro-PER (resample songs)."""
    import random
    rng = random.Random(seed)
    N = len(rows)
    if not N:
        return (float("nan"), float("nan"))
    stats = []
    for _ in range(n_boot):
        sample = [rows[rng.randrange(N)] for _ in range(N)]
        m, _, _ = micro(sample)
        stats.append(m)
    stats.sort()
    return stats[int(0.025 * n_boot)], stats[int(0.975 * n_boot)]


def load_json(p: Path):
    return json.loads(p.read_text()) if p.is_file() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--evidence-out", type=Path, default=None)
    args = ap.parse_args()

    out = {"label": args.label, "run": str(args.run)}
    scores = load_json(args.run / "scores" / "summary.json")
    additional = load_json(args.run / "additional" / "summary.json")
    audit = load_json(args.run / "audit.json")

    def grab(d, group="standard_selected", metric=None):
        if not d:
            return None
        g = d.get(group, {}).get("groups", {}).get("all", {})
        return g

    out["audit"] = {k: audit.get(k) for k in ("verdict", "verified_complete",
                                              "truncated_but_complete",
                                              "identity_reverified")} if audit else None
    sel = grab(scores) or {}
    unsel = grab(scores, "unselected_candidates") or {}
    out["selected"] = sel
    out["unselected"] = unsel
    out["additional_selected"] = grab(additional) or {}

    per_song = args.run / "scores" / "per_song.jsonl"
    if per_song.is_file():
        rows = [json.loads(l) for l in per_song.read_text().splitlines()
                if l.strip() and json.loads(l).get("metrics", {}).get("per", {}).get("per") is not None]
        P = lambda r: r["metrics"]["per"]
        done = [r for r in rows if r.get("status") != "failed"]
        capped = [r for r in done if P(r).get("truncated")]
        uncapped = [r for r in done if not P(r).get("truncated")]
        empty = [r for r in done
                 if not (P(r)["asr_repeats"][0].get("text") or "").strip()]
        best = {}
        for r in done:
            pid = r["prompt_index"]
            if pid not in best or P(r)["per"] < P(best[pid])["per"]:
                best[pid] = r
        bs = list(best.values())
        m_unsel, e_u, n_u = micro(done)
        m_sel, e_s, n_s = micro(bs)
        m_cap, _, _ = micro(capped)
        m_uncap, _, _ = micro(uncapped)
        lo, hi = bootstrap_ci_micro(bs)
        out["per_analysis"] = {
            "n_scored": len(done),
            "micro_unselected_all": round(m_unsel, 6),
            "micro_selected_192": round(m_sel, 6),
            "selected_bootstrap95": [round(lo, 6), round(hi, 6)],
            "capped_samples": len(capped),
            "capped_micro": round(m_cap, 6) if capped else None,
            "uncapped_micro": round(m_uncap, 6),
            "empty_transcript_candidates": len(empty),
            "per_eq_1": sum(1 for r in done if P(r)["per"] >= 0.999),
            "selected_per_gt_030": sum(1 for r in bs if P(r)["per"] > 0.30),
            "lang_split": {},
        }
        for lg in ("zh", "en"):
            lr = [r for r in bs if r.get("lang") == lg]
            m, _, _ = micro(lr)
            out["per_analysis"]["lang_split"][lg] = {
                "n": len(lr), "micro": round(m, 6),
                "capped": sum(1 for r in lr if P(r).get("truncated"))}

    text = json.dumps(out, indent=1)
    print(text)
    if args.evidence_out:
        args.evidence_out.mkdir(parents=True, exist_ok=True)
        (args.evidence_out / "campaign_summary.json").write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
