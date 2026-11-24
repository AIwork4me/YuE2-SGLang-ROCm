#!/usr/bin/env python3
"""rc5_select_pilot.py — PRE-REGISTERED pilot prompt selection (RC5 M3.3).

The six pilot prompts are chosen by rules fixed BEFORE any RC5 audio exists,
from the frozen manifest, the frozen evaluator targets and the HISTORICAL
per-prompt PER record. No result of this run can influence the selection.

Rules (in this order; a prompt already picked is replaced by the next best
of the same category):
  P1 zh-short   shortest lyrics (characters) among Mandarin prompts
  P2 zh-long    longest  lyrics (characters) among Mandarin prompts
  P3 en-short   shortest lyrics among English prompts
  P4 en-long    longest  lyrics among English prompts
  P5 boundary   largest style+lyrics character count overall (input boundary)
  P6 hist-high  highest historical Arm B selected PER (evidence file)

Usage:
  python scripts/rc5_select_pilot.py --workspace /data/yue2 --out reports/w7900_rc5/03_PILOT_SELECTION.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from pathlib import Path


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--evaluator-root", type=Path, default=None)
    ap.add_argument("--historical-per", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    ws = a.workspace
    ev = a.evaluator_root or ws / "benchmark/WildSongBench/wsb_metrics"
    manifest = ws / "benchmark/WildSongBench/benchmark/reproduction_manifest.jsonl"
    rows = [json.loads(l) for l in manifest.read_text().splitlines() if l.strip()]
    assert len(rows) == 192
    targets = {r["prompt_index"]: r for r in
               (json.loads(l) for l in (ev / "data/evaluation_targets.jsonl").read_text().splitlines() if l.strip())}
    hist_path = a.historical_per or Path(__file__).resolve().parents[1] / "evidence/per_prompt_scores.csv"
    hist = {int(r["prompt_index"]): float(r["selected_per"])
            for r in csv.DictReader(hist_path.read_text().splitlines())}

    def lang(i):
        return targets[i]["lang"]
    langs = sorted({lang(i) for i in range(192)})
    zh = [i for i in range(192) if lang(i).lower().startswith("zh")]
    en = [i for i in range(192) if lang(i).lower().startswith("en")]
    nlyr = {i: len(rows[i]["lyrics"]) for i in range(192)}
    nin = {i: len(rows[i]["style"]) + len(rows[i]["lyrics"]) for i in range(192)}

    picks, used = [], set()

    def take(category, ordered, metric):
        for i in ordered:
            if i not in used:
                used.add(i)
                picks.append({"category": category, "prompt_index": i, "lang": lang(i),
                              "selection_metric": {k: v[i] for k, v in metric.items()},
                              "style_chars": len(rows[i]["style"]),
                              "lyrics_chars": nlyr[i]})
                return
        raise RuntimeError(f"no candidate left for {category}")

    take("P1-zh-short", sorted(zh, key=lambda i: (nlyr[i], i)), {"lyrics_chars": nlyr})
    take("P2-zh-long", sorted(zh, key=lambda i: (-nlyr[i], i)), {"lyrics_chars": nlyr})
    take("P3-en-short", sorted(en, key=lambda i: (nlyr[i], i)), {"lyrics_chars": nlyr})
    take("P4-en-long", sorted(en, key=lambda i: (-nlyr[i], i)), {"lyrics_chars": nlyr})
    take("P5-boundary-largest-input", sorted(range(192), key=lambda i: (-nin[i], i)),
         {"style_plus_lyrics_chars": nin})
    take("P6-historical-highest-PER", sorted(range(192), key=lambda i: (-hist.get(i, -1), i)),
         {"historical_selected_per": hist})
    for p in picks:
        p["historical_selected_per"] = hist.get(p["prompt_index"])
    out = {
        "schema": "yue2-rc5-pilot-selection/1",
        "registered_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "preregistered": True,
        "rule": "fixed before generation; see module docstring of scripts/rc5_select_pilot.py",
        "languages_in_frozen_targets": langs,
        "zh_prompts": len(zh), "en_prompts": len(en),
        "inputs_sha256": {
            "reproduction_manifest.jsonl": sha256_file(manifest),
            "evaluation_targets.jsonl": sha256_file(ev / "data/evaluation_targets.jsonl"),
            "historical_per_prompt_scores.csv": sha256_file(hist_path),
        },
        "expected_candidates": 2 * len(picks),
        "picks": picks,
        "indices": [p["prompt_index"] for p in picks],
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: out[k] for k in ("indices", "expected_candidates")}))
    for p in picks:
        print(f"  {p['category']:28s} prompt {p['prompt_index']:3d} lang={p['lang']} "
              f"{p['selection_metric']} lyrics_chars={p['lyrics_chars']} "
              f"hist_PER={p['historical_selected_per']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
