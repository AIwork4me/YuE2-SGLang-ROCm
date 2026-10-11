#!/usr/bin/env python3
"""Emit a WSB run checkpoint status (used at 10/50/100/192/300/384 milestones).

Usage: python scripts/checkpoint_wsb.py --runs runs/wsb_full
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    args = ap.parse_args()

    rows = []
    mf = args.runs / "generation_manifest.jsonl"
    if mf.is_file():
        rows = [json.loads(l) for l in mf.read_text().splitlines() if l.strip()]
    complete = [r for r in rows if str(r.get("status", "")).startswith("complete")]
    failed = [r for r in rows if r.get("status") in ("generation_failed", "finalize_failed")]
    walls = [r["wall_s"] for r in complete if r.get("wall_s")]
    audios = [r["audio_seconds"] for r in complete if r.get("audio_seconds")]
    truncated = sum(1 for r in complete if r.get("truncated"))
    gtt = 0
    try:
        for p in Path("/sys/class/drm/card1/device").glob("mem_info_gtt_used"):
            gtt = int(p.read_text())
    except OSError:
        pass
    report = {
        "run": str(args.runs),
        "complete": len(complete),
        "failed": len(failed),
        "records_total": len(rows),
        "pending": max(0, 384 - len(complete) - len(failed)),
        "truncated_complete": truncated,
        "wall_s_median": round(statistics.median(walls), 1) if walls else None,
        "wall_s_mean": round(statistics.mean(walls), 1) if walls else None,
        "audio_s_mean": round(statistics.mean(audios), 1) if audios else None,
        "eta_h_full_run": round(len(walls) and statistics.mean(walls) * (384 - len(complete)) / 3600, 1),
        "gtt_used_bytes": gtt,
        "disk_free": subprocess.run(["df", "-h", "/"], capture_output=True, text=True).stdout.splitlines()[1].split()[3],
        "server_commit": "sglang ced0ef7d + patches 0001-0005",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
