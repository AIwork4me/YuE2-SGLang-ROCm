#!/usr/bin/env python3
"""rc4_perf_dataset.py — build the RC4 performance raw CSV and aggregates.

Sources (never invented numbers):
  1. Frozen campaign receipts (Arm A/B generation_manifest.jsonl) — measured
     under gpu_lock single-tenant windows on THIS GPU with the frozen stack;
     marked source=campaign_frozen. Reuse is explicitly allowed by the RC4
     mission ("no redundant benchmark cases that already have sufficient
     evidence unless the stack changed" — the stack is unchanged: same
     sglang commit, patchset, model/VAE/dataset pins, torch builds).
  2. RC4 fresh measurements (JSON receipts written by rc4 measurement runs)
     — marked source=rc4_fresh.

Output columns follow reports/w7900_rc4/03_PERFORMANCE_RAW.csv as specified
by the mission (M3.6). Aggregates are computed from the raw rows only.

Usage:
  python3 scripts/rc4_perf_dataset.py --out reports/w7900_rc4/03_PERFORMANCE_RAW.csv \
      [--armA /data/yue2-runs/armA_wsb_full] [--armB /data/yue2-runs/armB_wsb_full] \
      [--fresh-dir /data/yue2-runs/rc4_perf]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from pathlib import Path


def campaign_rows(run: Path, backend: str, git_sha: str, env: dict) -> list[dict]:
    rows = []
    mf = run / "generation_manifest.jsonl"
    rc = json.loads((run / "run_config.json").read_text())
    for line in mf.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("status") != "complete" or not r.get("wall_s"):
            continue
        audio = r.get("audio_seconds") or 0.0
        wall = float(r["wall_s"])
        rows.append({
            "run_id": rc.get("run_id", run.name),
            "git_sha": git_sha,
            "model_revision": rc.get("model_revision", ""),
            "backend": backend,
            "gpu": env["gpu"], "rocm_version": env["rocm"],
            "torch_version": rc.get("torch", env["torch"]),
            "sglang_revision": rc.get("sglang_commit", ""),
            "prompt_id": f"wsb_{r['prompt_index']:03d}",
            "seed": r["seed"],
            "cold_or_warm": "campaign_window",
            "client_concurrency": 1, "actual_gpu_batch": 1,
            "status": "complete",
            "wall_seconds": round(wall, 2),
            "audio_seconds": round(audio, 2),
            "audio_realtime_multiplier": round(audio / wall, 4) if wall and audio else "",
            "peak_vram_bytes": rc.get("peak_vram_bytes", ""),
            "peak_gtt_bytes": rc.get("peak_gtt_bytes", ""),
            "peak_rss_bytes": "",
            "failure_reason": "",
            "receipt_path": str(mf),
            "source": "campaign_frozen",
        })
    return rows


def fresh_rows(d: Path) -> list[dict]:
    rows = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        r = json.loads(f.read_text())
        wall = float(r.get("wall_seconds") or 0)
        audio = float(r.get("audio_seconds") or 0)
        rows.append({
            "run_id": r.get("run_id", ""), "git_sha": r.get("git_sha", ""),
            "model_revision": r.get("model_revision", ""),
            "backend": r.get("backend", ""), "gpu": r.get("gpu", ""),
            "rocm_version": r.get("rocm_version", ""),
            "torch_version": r.get("torch_version", ""),
            "sglang_revision": r.get("sglang_revision", ""),
            "prompt_id": r.get("prompt_id", ""), "seed": r.get("seed", ""),
            "cold_or_warm": r.get("cold_or_warm", ""),
            "client_concurrency": r.get("client_concurrency", 1),
            "actual_gpu_batch": r.get("actual_gpu_batch", ""),
            "status": r.get("status", ""), "wall_seconds": round(wall, 2),
            "audio_seconds": round(audio, 2),
            "audio_realtime_multiplier": round(audio / wall, 4) if wall and audio else "",
            "peak_vram_bytes": r.get("peak_vram_bytes", ""),
            "peak_gtt_bytes": r.get("peak_gtt_bytes", ""),
            "peak_rss_bytes": r.get("peak_rss_bytes", ""),
            "failure_reason": r.get("failure_reason", ""),
            "receipt_path": str(f), "source": "rc4_fresh",
        })
    return rows


def agg(rows: list[dict]) -> dict:
    walls = [float(r["wall_seconds"]) for r in rows]
    rtms = [float(r["audio_realtime_multiplier"]) for r in rows
            if r["audio_realtime_multiplier"] != ""]
    def p95(v):
        v = sorted(v)
        i = max(0, min(len(v) - 1, int(round(0.95 * (len(v) - 1)))))
        return v[i]
    return {
        "n": len(rows),
        "p50_wall_s": round(st.median(walls), 1) if walls else None,
        "p95_wall_s": round(p95(walls), 1) if walls else None,
        "mean_wall_s": round(st.mean(walls), 1) if walls else None,
        "min_wall_s": round(min(walls), 1) if walls else None,
        "max_wall_s": round(max(walls), 1) if walls else None,
        "mean_audio_realtime_multiplier": round(st.mean(rtms), 4) if rtms else None,
        "p95_audio_realtime_multiplier": round(p95(rtms), 4) if rtms else None,
        "failures": sum(1 for r in rows if r["status"] not in ("complete", "ok")),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--armA", type=Path, default=Path("/data/yue2-runs/armA_wsb_full"))
    ap.add_argument("--armB", type=Path, default=Path("/data/yue2-runs/armB_wsb_full"))
    ap.add_argument("--fresh-dir", type=Path, default=Path("/data/yue2-runs/rc4_perf"))
    ap.add_argument("--summary", type=Path, default=None)
    args = ap.parse_args()

    env = {"gpu": "AMD Radeon PRO W7900D 48GB (gfx1100)",
           "rocm": "7.2.1 host / 7.14.1 userspace wheels",
           "torch": "see run_config"}
    rows = []
    if args.armA.is_dir():
        rows += campaign_rows(args.armA, "armA_native_torch_eager",
                              "48d1cb6 (RC4 base; campaign at c1e0445 patchset)", env)
    if args.armB.is_dir():
        rows += campaign_rows(args.armB, "armB_sglang_serving",
                              "48d1cb6 (RC4 base; campaign at c1e0445 patchset)", env)
    rows += fresh_rows(args.fresh_dir)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by: dict = {}
    for r in rows:
        by.setdefault((r["backend"], r["source"], r["cold_or_warm"]), []).append(r)
    summary = {f"{k[0]}|{k[1]}|{k[2]}": agg(v) for k, v in sorted(by.items())}
    text = json.dumps({"rows_total": len(rows), "aggregates": summary}, indent=1)
    print(text)
    if args.summary:
        args.summary.write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
