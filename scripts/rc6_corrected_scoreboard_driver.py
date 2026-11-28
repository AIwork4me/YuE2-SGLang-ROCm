#!/usr/bin/env python3
"""rc6_corrected_scoreboard_driver.py — RC6 A3.3 (Scoreboard B driver).

Scores SongBench / MuLan / AllMusicCaps on the vLLM-CORRECTED selection
(S_V, 07_CORRECTED_SELECTION_MANIFEST.json) using the FROZEN OFFICIAL
evaluator code end-to-end:

  verify_release + verify_assets (official integrity gates)
  prepare_inputs on the frozen 384-row input (official validation + MP3
    encoding, cached) — then filter to the 192 S_V candidates
  per-metric identity + jobs + OFFICIAL worker subprocess (same venvs
    wsb_eval.py itself uses: .venvs/eval for songbench, .venvs/metrics for
    mulan/allmusiccaps)
  read_cached + canonical_songbench (official receipt loading)
  extended_eval.summarize (the official aggregation used for
    'standard_selected' in the RC5.1 frozen scoreboard)

The ONLY scientific variable vs Scoreboard A is the candidate SET (S_V from
the corrected vLLM PER arm instead of S_T from the frozen transformers arm)
— disclosed everywhere the numbers appear. Selection is NOT re-derived
here; it is the frozen S_V manifest.

Usage (from the evaluator parent dir, under the GPU lock):
  $WS/environments/yue2-gfx1100/bin/python scripts/rc6_corrected_scoreboard_driver.py \
      --input <frozen evaluation_inputs.jsonl> --report <out dir> \
      --sv reports/w7900_rc5/rc5_1/07_CORRECTED_SELECTION_MANIFEST.json \
      [--metrics songbench,mulan,allmusiccaps]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent / "benchmark/wsb_metrics" if False else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator-root", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--sv", type=Path, required=True)
    ap.add_argument("--metrics", default="songbench,mulan,allmusiccaps")
    a = ap.parse_args()
    root = a.evaluator_root
    sys.path[:0] = [str(root / "src"), str(root / "vendor"), str(root)]
    import wsb_eval as W
    from mot_infer import extended_eval
    from mot_infer.io import write_json

    metrics = W.names(a.metrics)
    report = a.report.resolve()
    report.mkdir(parents=True, exist_ok=True)

    release = W.verify_release()
    hashes = W.verify_assets(metrics)
    config = json.loads((root / "configs/evaluation.json").read_text())

    # official input preparation over the FULL frozen 384 rows (validation +
    # MP3 encoding happen here; audio/ is already cached from the first
    # attempt), then filter to the frozen corrected selection.
    rows = W.prepare_inputs(a.input.resolve(), report, "standard")
    sv_ids = [c["id"] for c in json.loads(a.sv.read_text())["candidates"]]
    by_id = {r["id"]: r for r in rows}
    missing = [i for i in sv_ids if i not in by_id]
    if missing:
        print(f"FATAL: {len(missing)} S_V ids not in input: {missing[:5]}")
        return 2
    sel = [by_id[i] for i in sv_ids]
    print(f"[selv] selected rows: {len(sel)} (frozen S_V manifest "
          f"{a.sv.name}); input rows prepared: {len(rows)}", flush=True)

    for metric in metrics:
        jobs = []
        for row in sel:
            key = extended_eval.identity(row, metric, config, hashes, release["code_files"])
            path = report / "receipts" / row["id"] / (metric + ".json")
            if extended_eval.read_cached(path, key) is None:
                jobs.append({**row, "identity": key, "result_path": str(path)})
        jobfile = report / (metric + ".jobs.json")
        write_json(jobfile, {"jobs": jobs, "config": config})
        if jobs:
            python = (root / ".venvs/eval/bin/python" if metric == "songbench"
                      else root / ".venvs/metrics/bin/python")
            if not python.is_file():
                print(f"FATAL: worker venv missing for {metric}: {python}")
                return 2
            print(f"[selv] {metric}: {len(jobs)} jobs -> {python.name}", flush=True)
            t0 = time.time()
            with (report / (metric + ".log")).open("a") as stream:
                proc = subprocess.run(
                    [str(python), str(root / "wsb_eval.py"), "_worker",
                     "--metric", metric, "--jobs", str(jobfile)],
                    env=W.environment(report), stdout=stream, stderr=subprocess.STDOUT)
            print(f"[selv] {metric}: worker exit {proc.returncode} "
                  f"({time.time()-t0:.0f}s)", flush=True)
            if proc.returncode != 0:
                return proc.returncode
        else:
            print(f"[selv] {metric}: all receipts cached", flush=True)

    for row in sel:
        row.setdefault("metrics", {})
        for metric in metrics:
            path = report / "receipts" / row["id"] / (metric + ".json")
            key = extended_eval.identity(row, metric, config, hashes, release["code_files"])
            value = extended_eval.read_cached(path, key)
            if value is None:
                value = {"status": "failed",
                         "error": "No complete worker receipt matching this exact "
                                  "audio, target, code and configuration identity"}
            row["metrics"][metric] = (W.canonical_songbench(value) if metric == "songbench"
                                      else value)

    summary = extended_eval.summarize(sel, metrics)
    summary["selection"] = {
        "arm": "vLLM-corrected selection S_V (frozen 07_CORRECTED_SELECTION_MANIFEST.json)",
        "selection_rule": "official ordering key over the E2 corrected PER arm "
                          "(per, edits, abs phoneme diff, candidate_index)",
        "note": "same official scorers/aggregation as Scoreboard A; ONLY the candidate set "
                "differs (disclosed); never mixed with Scoreboard A",
        "sv_manifest": str(a.sv),
    }
    write_json(report / "summary_selv.json", summary)
    head = {}
    for metric in metrics:
        b = summary["groups"]["all"].get(metric) or {}
        head[metric] = b.get("means") or {"per_micro": b.get("per_micro")}
    print(json.dumps({"selv_headline_means": head,
                      "samples": summary["samples"],
                      "complete": summary["complete"]}, indent=1))
    return 0 if summary["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
