#!/usr/bin/env python3
"""collect_performance.py - assemble the gfx1100 performance baseline.

Sources (no synthetic numbers):
  - <run>/generation_manifest.jsonl : per-candidate wall_s, audio_seconds,
    truncated, retries, wav archive moves
  - server log                      : per-request stage timings
    (Yue2ARStage/Yue2NARStage/Yue2VAEDecodeStage "finished in X seconds")
  - rocm-smi samples                : peak VRAM/GTT from generation_summary.json

Output: JSON + optional CSV (one row per candidate).
Usage: python collect_performance.py --runs DIR [--server-log LOG] [--out OUT.json]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from collections import defaultdict
from pathlib import Path


def parse_server_stages(log: Path):
    """Pair stage durations into per-request records (chronological)."""
    if not log.is_file():
        return []
    reqs, cur = [], {}
    pat = re.compile(r"\[(?P<ts>[\d\- :]+)\] \[Yue2(?P<stage>\w+)Stage\] "
                     r"(?:started|finished in (?P<secs>[\d.]+) seconds)")
    # finished lines: "finished in X seconds"
    fin = re.compile(r"\[Yue2(?P<stage>\w+)Stage\] finished in (?P<secs>[\d.]+) seconds")
    for line in log.read_text(errors="replace").splitlines():
        m = fin.search(line)
        if not m:
            continue
        stage, secs = m.group("stage"), float(m.group("secs"))
        cur[stage] = secs
        if stage == "VAEDecode":  # last stage of a request
            reqs.append(dict(cur))
            cur = {}
    return reqs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--server-log", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    manifest = args.runs / "generation_manifest.jsonl"
    recs = [json.loads(l) for l in manifest.read_text().splitlines()] if manifest.is_file() else []
    complete = {}
    for r in recs:
        if r.get("status", "").startswith("complete"):
            complete[r["id"]] = r
    rows = sorted(complete.values(), key=lambda r: (r["prompt_index"], r["candidate_index"]))

    stages = parse_server_stages(args.server_log) if args.server_log else []
    summary_path = args.runs / "generation_summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}

    walls = [r["wall_s"] for r in rows if "wall_s" in r]
    audio = [r["audio_seconds"] for r in rows if "audio_seconds" in r]
    ar = [s["AR"] for s in stages if "AR" in s]
    nar = [s["NAR"] for s in stages if "NAR" in s]
    vae = [s["VAEDecode"] for s in stages if "VAEDecode" in s]

    def stats(xs):
        if not xs:
            return None
        return {"n": len(xs), "mean": round(statistics.mean(xs), 2),
                "median": round(statistics.median(xs), 2),
                "min": round(min(xs), 2), "max": round(max(xs), 2)}

    out = {
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run": str(args.runs),
        "candidates_complete": len(rows),
        "truncated": sum(1 for r in rows if r.get("truncated")),
        "retried": sum(1 for r in recs if r.get("retries")),
        "wall_s": stats(walls),
        "audio_s": stats(audio),
        "stage_ar_s": stats(ar),
        "stage_nar_s": stats(nar),
        "stage_vae_s": stats(vae),
        "audio_sec_per_wall_sec": round(statistics.mean(audio) / statistics.mean(walls), 4)
        if audio and walls else None,
        "peak_vram_bytes": summary.get("peak_vram_bytes"),
        "peak_gtt_bytes": summary.get("peak_gtt_bytes"),
        "per_candidate": [{"id": r["id"], "wall_s": r.get("wall_s"),
                           "audio_s": r.get("audio_seconds"),
                           "truncated": r.get("truncated")} for r in rows],
    }
    dest = args.out or (args.runs / "performance_baseline.json")
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "per_candidate"}, indent=1))
    print("written:", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
