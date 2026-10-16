#!/usr/bin/env python3
"""bench_serving_omni.py - BS=1 latency and concurrency sweep for the
SGLang-Omni YuE2 server on gfx1100.

Phase 4 (BS=1):  SGLANG_YUE2_BATCH_MAX_SIZE=1, client concurrency=1.
Phase 5 (sweep): GPU batch stays 1; client concurrency C in {1,2,4,8(,16)};
                 closed-loop load generator over a fixed WSB prompt/seed mix.

Measures per completed request: end-to-end latency, generated audio seconds
(from WAV frames), RTF (audio_s / wall_s), HTTP status, finish reason.
Polls VRAM/GTT and GPU utilization while running. Raw JSONL per request is
written continuously; a summary JSON is written at the end of each stage.

YuE2 nested input JSON is used verbatim from the frozen WSB manifest rows
(short mix for the serving benchmark is a documented, separate workload from
the WSB quality arm and never scored as WSB output).
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import threading
import time
import wave
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MANIFEST = Path("/workspace/yue2-sglang-rocm-w7900/benchmark/WildSongBench/"
                "benchmark/reproduction_manifest.jsonl")


def rows():
    return [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]


def gpu_snapshot():
    vram = gtt = 0
    for card in Path("/sys/class/drm").glob("card*"):
        try:
            v = card / "device/mem_info_vis_vram_used"
            g = card / "device/mem_info_gtt_used"
            if v.is_file():
                vram = max(vram, int(v.read_text()))
            if g.is_file():
                gtt = max(gtt, int(g.read_text()))
        except (OSError, ValueError):
            continue
    util = 0
    try:
        out = subprocess.run(["rocm-smi", "--showuse", "--csv"],
                             capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            if line.startswith("card") and "%" not in line and "," in line:
                try:
                    util = max(util, int(line.split(",")[-1].strip()))
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass
    return vram, gtt, util


class Monitor(threading.Thread):
    def __init__(self, interval=2.0):
        super().__init__(daemon=True)
        self.interval = interval
        self.stop = threading.Event()
        self.peak_vram = 0
        self.peak_gtt = 0
        self.util_samples: list[int] = []

    def run(self):
        while not self.stop.is_set():
            vram, gtt, util = gpu_snapshot()
            self.peak_vram = max(self.peak_vram, vram)
            self.peak_gtt = max(self.peak_gtt, gtt)
            self.util_samples.append(util)
            self.stop.wait(self.interval)


def one_request(server, row, seed, timeout):
    nested = {
        "style": row["style"], "lyrics": row["lyrics"],
        "cot": "full", "seed": seed, "cfg_scale": 1.0,
        "abc_max_tokens": 4096, "semantic_max_tokens": 9000,
        "ode_steps": 32, "vae_core_frames": 1024, "vae_halo_frames": 16,
    }
    payload = {"model": "yue2", "input": json.dumps(nested, ensure_ascii=False),
               "voice": "default", "response_format": "wav"}
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(f"{server}/v1/audio/speech",
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            wall = time.perf_counter() - t0
            rec = {"ok": resp.status == 200,
                   "status": resp.status,
                   "finish_reason": resp.headers.get("x-finish-reason"),
                   "wall_s": round(wall, 3),
                   "bytes": len(body)}
            if body[:4] == b"RIFF":
                with wave.open(__import__("io").BytesIO(body)) as w:
                    rec["audio_s"] = round(w.getnframes() / w.getframerate(), 3)
                    rec["rate"] = w.getframerate()
                    rec["channels"] = w.getnchannels()
            else:
                rec["ok"] = False
                rec["error"] = "not RIFF"
            return rec
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "wall_s": round(time.perf_counter() - t0, 3)}


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return round(s[k], 3)


def run_stage(server, tag, items, concurrency, out_dir, timeout, warmup=0):
    """Closed-loop: `concurrency` workers, each takes the next item until done."""
    raw_path = out_dir / f"raw_{tag}_C{concurrency}.jsonl"
    mon = Monitor()
    mon.start()
    queue = list(items)
    lock = threading.Lock()
    results = []

    def worker():
        while True:
            with lock:
                if not queue:
                    return
                idx, row, seed = queue.pop(0)
            rec = one_request(server, row, seed, timeout)
            rec["item"] = idx
            results.append(rec)
            with raw_path.open("a") as f:
                f.write(json.dumps(rec) + "\n")

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(ex.map(lambda _: worker(), range(concurrency)))
    wall = time.perf_counter() - t0
    mon.stop.set()
    mon.join(timeout=10)

    ok = [r for r in results if r.get("ok")]
    lat = [r["wall_s"] for r in ok]
    auds = [r["audio_s"] for r in ok]
    summary = {
        "tag": tag, "concurrency": concurrency, "issued": len(items),
        "completed_ok": len(ok), "errors": len(results) - len(ok),
        "wall_s": round(wall, 3),
        "rps": round(len(ok) / wall, 4) if wall else None,
        "audio_s_total": round(sum(auds), 3),
        "audio_s_per_wall_s": round(sum(auds) / wall, 4) if wall else None,
        "latency_p50_s": pct(lat, 50), "latency_p95_s": pct(lat, 95),
        "latency_p99_s": pct(lat, 99), "latency_mean_s":
            round(statistics.mean(lat), 3) if lat else None,
        "audio_s_mean": round(statistics.mean(auds), 3) if auds else None,
        "rtf_mean": round(statistics.mean(a / r["wall_s"] for r, a in
                                          zip(ok, auds)), 4) if ok else None,
        "peak_vram_bytes": mon.peak_vram, "peak_gtt_bytes": mon.peak_gtt,
        "gpu_util_mean_pct": round(statistics.mean(mon.util_samples), 1)
        if mon.util_samples else None,
        "gpu_util_p90_pct": pct([float(u) for u in mon.util_samples], 90),
        "error_detail": [r.get("error") for r in results if not r.get("ok")][:10],
    }
    (out_dir / f"summary_{tag}_C{concurrency}.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:32100")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mode", choices=["bs1", "sweep"], required=True)
    ap.add_argument("--indices", type=int, nargs="*", default=None,
                    help="WSB prompt indices for the fixed serving mix")
    ap.add_argument("--repeats", type=int, default=3,
                    help="repetitions of the mix per stage")
    ap.add_argument("--warmup", type=int, default=1,
                    help="warmup requests before measurement (not counted)")
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--concurrencies", type=int, nargs="*", default=[1, 2, 4, 8])
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    all_rows = rows()
    mix_indices = args.indices or [0, 22, 63, 75, 100, 120, 150, 170]
    mix_rows = [(i, all_rows[i]) for i in mix_indices]
    cfg = {"server": args.server, "mix_indices": mix_indices,
           "repeats": args.repeats, "warmup": args.warmup,
           "frozen_manifest_sha_rows": len(all_rows)}
    (args.out / "bench_config.json").write_text(json.dumps(cfg, indent=2) + "\n")

    items = []
    for rep in range(args.repeats):
        for i, row in mix_rows:
            items.append((f"{i}_r{rep}", row, row["candidate_ar_seeds"][rep % 2]))

    if args.warmup:
        print(f"[warmup] {args.warmup} request(s) (excluded from metrics)", flush=True)
        for k in range(args.warmup):
            i, row = mix_rows[k % len(mix_rows)]
            r = one_request(args.server, row, row["candidate_ar_seeds"][1], args.timeout)
            print(f"[warmup {k+1}] ok={r.get('ok')} wall={r.get('wall_s')}s "
                  f"audio={r.get('audio_s')}s", flush=True)

    stages = ([1] if args.mode == "bs1" else args.concurrencies)
    for c in stages:
        print(f"[stage] C={c} issuing {len(items)} requests ...", flush=True)
        s = run_stage(args.server, args.mode, items, c, args.out, args.timeout)
        print(json.dumps(s, indent=2), flush=True)


if __name__ == "__main__":
    main()
