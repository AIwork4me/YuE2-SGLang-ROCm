#!/usr/bin/env python3
"""scoring_stage_check.py - stage-completeness checks for the v2 pipeline.

The resume/skip logic must NOT trust file existence, row counts, or even
summary flags alone: wsb_eval.py rewrites summary.json after EVERY metric
iteration, so a hard crash after PER finishes (before SongBench starts) leaves
a per-only summary that still says complete=true and
full_192_standard_candidate_coverage=true. We therefore ALSO require the
per-metric blocks (written by extended_eval.summarize) for every official
metric of the stage to be present and non-empty.

Stage 5 (per,songbench):  scores/summary.json
    complete == true AND full_192_standard_candidate_coverage == true
    AND per_song.jsonl >= 384 rows
    AND metric blocks {per, songbench} present in unselected_candidates
Stage 6 (mulan,allmusiccaps): additional/summary.json
    complete == true AND full_192_selected_coverage == true
    AND metric blocks {mulan, allmusiccaps} present in unselected_candidates

Usage:
  scoring_stage_check.py per         <run_dir>   # exit 0 = stage 5 may be skipped
  scoring_stage_check.py additional <run_dir>   # exit 0 = stage 6 may be skipped
  scoring_stage_check.py per_song_rows <run_dir>
Exit 0 = officially complete (skip allowed); 1 = not complete; 2 = usage error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _load(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _metric_blocks(summary: dict) -> set:
    """Collect metric names present in the aggregate sections.

    Real schema (extended_eval.summarize): section = {"schema", "complete",
    "samples", "groups": {group: {metric: block}}, "metrics": [names]}.
    We read both the explicit metric list and the group blocks."""
    names = set()
    for section in ("unselected_candidates", "standard_selected"):
        agg = summary.get(section) or {}
        if not isinstance(agg, dict):
            continue
        if isinstance(agg.get("metrics"), list):
            names |= {str(m) for m in agg["metrics"]}
        groups = agg.get("groups")
        if isinstance(groups, dict):
            for _, blocks in groups.items():
                if isinstance(blocks, dict):
                    names |= {k for k, v in blocks.items()
                              if isinstance(v, dict) and "scored" in v}
        elif isinstance(groups, dict) is False and isinstance(agg.get("groups"), dict) is False:
            # tolerate legacy shape: section directly = {group: {metric: block}}
            for _, blocks in agg.items():
                if isinstance(blocks, dict):
                    names |= {k for k, v in blocks.items()
                              if isinstance(v, dict) and "scored" in v}
    return names


def _stage_complete(run: Path, summary_path: Path, flags: tuple,
                    metrics: tuple, min_rows: int = 0) -> bool:
    s = _load(run / summary_path)
    if not isinstance(s, dict):
        return False
    if s.get("complete") is not True:
        return False
    for flag in flags:
        if s.get(flag) is not True:
            return False
    blocks = _metric_blocks(s)
    if not set(metrics) <= blocks:
        return False
    if min_rows:
        per_song = run / "scores" / "per_song.jsonl"
        if not per_song.is_file():
            return False
        rows = sum(1 for l in per_song.read_text().splitlines() if l.strip())
        if rows < min_rows:
            return False
    return True


def per_complete(run: Path) -> bool:
    return _stage_complete(
        run, Path("scores/summary.json"),
        flags=("full_192_standard_candidate_coverage",),
        metrics=("per", "songbench"), min_rows=384)


def additional_complete(run: Path) -> bool:
    return _stage_complete(
        run, Path("additional/summary.json"),
        flags=("full_192_selected_coverage",),
        metrics=("mulan", "allmusiccaps"))


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    what, run = argv[1], Path(argv[2])
    if what == "per":
        ok = per_complete(run)
    elif what == "additional":
        ok = additional_complete(run)
    elif what == "per_song_rows":
        p = run / "scores" / "per_song.jsonl"
        print(sum(1 for l in p.read_text().splitlines() if l.strip())
              if p.is_file() else 0)
        return 0
    else:
        print(__doc__)
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
