#!/usr/bin/env python3
"""RC2 PER length-effect analysis (mission §5.3, CPU-only, aggregates only).

Question: does PER co-vary with song length, lyrics (reference phoneme)
length, or ASR output length — and is the error direction net-short
(deletion-dominant, ASR under-transcription) or net-long (insertion-dominant)?
Restricted text never leaves the receipts; this script emits COUNTS and
AGGREGATES only.

Inputs (frozen):
  --per-song   scores/per_song.jsonl   (official frozen scorer receipts)
  --manifest   generation_manifest.jsonl (audio_seconds per candidate)
  --out        aggregates JSON path

Denominator discipline: selected-192 via the official summary's
selected_candidates when available next to per_song.jsonl (summary.json in
the same directory); otherwise diagnostic min-selection, labeled as such.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path


def ranks(v):
    order = {x: i for i, x in enumerate(sorted(v))}
    return [order[x] for x in v]


def spearman(x, y):
    rx, ry = ranks(x), ranks(y)
    return pearson(rx, ry)


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx = math.sqrt(sum((a - mx) ** 2 for a in x))
    vy = math.sqrt(sum((b - my) ** 2 for b in y))
    return cov / (vx * vy) if vx and vy else float("nan")


def boot_ci(vals, n=10000, seed=11):
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        s = [vals[rng.randrange(len(vals))] for _ in range(len(vals))]
        means.append(sum(s) / len(s))
    means.sort()
    return means[int(0.025 * n)], means[int(0.975 * n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-song", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--summary", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    rows = [json.loads(l) for l in a.per_song.read_text().splitlines() if l.strip()]
    gen = {r["id"]: r for r in
           (json.loads(l) for l in a.manifest.read_text().splitlines() if l.strip())
           if r.get("status", "").startswith("complete")}

    summ_path = a.summary or (a.per_song.parent / "summary.json")
    selected_ids = None
    if summ_path.is_file():
        s = json.loads(summ_path.read_text())
        sel = s.get("selected_candidates")
        if sel and isinstance(sel[0], dict):
            selected_ids = {r["id"] for r in sel if "id" in r}
            if not selected_ids:  # id-less entries: match on the triple
                keys = {(r.get("prompt_index"), r.get("candidate_index"),
                         r.get("seed")) for r in sel}
                selected_ids = {r["id"] for r in rows
                                if (r["prompt_index"], r["candidate_index"],
                                    r["seed"]) in keys}
        else:
            selected_ids = set(sel or [])
    if selected_ids is None:  # diagnostic fallback, explicitly labeled
        by_prompt = {}
        for r in rows:
            by_prompt.setdefault(r["prompt_index"], []).append(r)
        selected_ids = set()
        for _, cands in by_prompt.items():
            # Exact official frozen key (RC4 M4.2 fix): the previous fallback
            # used abs(reference_phonemes - per) — a phoneme COUNT minus the
            # PER RATE — and selected_asr_repeat as the final component, both
            # deviating from wsb_eval.py select_candidates.
            def _official_key(r):
                m = r["metrics"]["per"]
                rep = m["asr_repeats"][m["selected_asr_repeat"]]
                return (m["per"], m["edits"],
                        abs(len(rep["phonemes"]) - m["reference_phonemes"]),
                        r["candidate_index"])
            selected_ids.add(min(cands, key=_official_key)["id"])

    feats = []
    for r in rows:
        if r["id"] not in selected_ids:
            continue
        m = r["metrics"]["per"]
        asr_texts = [t.get("text", "") for t in (m.get("asr_repeats") or [])]
        sel = m.get("selected_asr_repeat")
        hyp = asr_texts[sel] if isinstance(sel, int) and 0 <= sel < len(asr_texts) else ""
        g = gen.get(r["id"], {})
        ref_phon = m["reference_phonemes"]
        feats.append({
            "id": r["id"], "lang": r["lang"],
            "per": m["per"], "edits": m["edits"],
            "ref_phonemes": ref_phon,
            "hyp_chars": len(hyp), "ref_chars": len(m.get("reference_lyrics") or ""),
            "net_chars": len(hyp) - len(m.get("reference_lyrics") or ""),
            "asr_truncated": bool(m.get("selected_asr_truncated")),
            "audio_seconds": g.get("audio_seconds"),
            "empty_transcript": (len(hyp.strip()) == 0),
        })

    def col(k):
        return [f[k] for f in feats if isinstance(f[k], (int, float))]

    out = {
        "n_selected": len(feats),
        "selection_source": "official summary.selected_candidates"
                            if (a.summary or (a.per_song.parent / "summary.json")).is_file()
                            else "diagnostic min (non-authoritative)",
        "spearman_per_vs": {},
        "pearson_per_vs": {},
        "direction": {},
        "empty_transcripts": sum(1 for f in feats if f["empty_transcript"]),
        "truncated_asr": sum(1 for f in feats if f["asr_truncated"]),
    }
    for k in ("ref_phonemes", "hyp_chars", "audio_seconds"):
        xs, ys = [], []
        for f in feats:
            if isinstance(f[k], (int, float)):
                xs.append(float(f[k])); ys.append(f["per"])
        out["spearman_per_vs"][k] = round(spearman(xs, ys), 4)
        out["pearson_per_vs"][k] = round(pearson(xs, ys), 4)

    net = [f["net_chars"] for f in feats]
    out["direction"] = {
        "mean_net_chars": round(sum(net) / len(net), 1),
        "ci95_net_chars": [round(v, 1) for v in boot_ci(net)],
        "candidates_net_negative": sum(1 for v in net if v < 0),
        "candidates_net_positive": sum(1 for v in net if v > 0),
        "interpretation_hint": ("net-negative dominance = hypothesis transcripts "
                                "shorter than references (deletion/under-transcription "
                                "signal); net-positive = insertion signal"),
    }
    for lang in ("zh", "en"):
        sub = [f["per"] for f in feats if f["lang"] == lang]
        if sub:
            out[f"per_{lang}_mean"] = round(sum(sub) / len(sub), 5)
            out[f"per_{lang}_ci95"] = [round(v, 5) for v in boot_ci(sub)]
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
