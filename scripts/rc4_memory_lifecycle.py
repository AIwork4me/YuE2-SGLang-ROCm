#!/usr/bin/env python3
"""rc4_memory_lifecycle.py — M2.6 native PyTorch close()/memory investigation.

Pre-registered sequence per reports/joint_blog_rc/04_RUNTIME_RCA_AND_RELIABILITY.md
(R3): load -> generate(short) -> close -> GC -> cache cleanup, N controlled
cycles (default 5), measuring at each stage:
  torch memory_allocated / memory_reserved / max_memory_allocated
  rocm-smi VRAM used / GTT used   (process-attributed where available)
  host RSS of THIS process
  process lifetime and actual GPU release after close()

Run INSIDE the native environment (yue2-torch venv):
  /path/to/yue2-torch/bin/python scripts/rc4_memory_lifecycle.py \
      --model /data/rc4/ws/models/YuE2-3B \
      --vae /data/rc4/ws/models/YuE2-Vae-legacy \
      --out /data/yue2-runs/rc4_evidence/02_MEMORY_LIFECYCLE.csv
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import subprocess
import time
from pathlib import Path

STAGES = ["before_load", "after_load", "after_generate", "after_close",
          "after_gc", "after_empty_cache"]


def gpu_mem() -> tuple[int | None, int | None]:
    """(vram_used_bytes, gtt_used_bytes) via rocm-smi (device totals)."""
    try:
        out = subprocess.run(["rocm-smi", "--showmeminfo", "vram", "--csv"],
                             capture_output=True, text=True, timeout=15).stdout
        vram = None
        for line in out.splitlines():
            if "VRAM Total Used Memory" in line:
                vram = int(line.split(",")[-1].strip())
        out2 = subprocess.run(["rocm-smi", "--showmeminfo", "gtt", "--csv"],
                              capture_output=True, text=True, timeout=15).stdout
        gtt = None
        for line in out2.splitlines():
            if "GTT Total Used Memory" in line:
                gtt = int(line.split(",")[-1].strip())
        return vram, gtt
    except Exception:
        return None, None


def snapshot(pipeline=None) -> dict:
    import torch
    rss = None
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1]) * 1024
                break
    except Exception:
        pass
    vram, gtt = gpu_mem()
    return {
        "torch_memory_allocated": torch.cuda.memory_allocated(0) if torch.cuda.is_available() else None,
        "torch_memory_reserved": torch.cuda.memory_reserved(0) if torch.cuda.is_available() else None,
        "torch_max_memory_allocated": torch.cuda.max_memory_allocated(0) if torch.cuda.is_available() else None,
        "rocm_vram_used": vram, "rocm_gtt_used": gtt, "host_rss": rss,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--vae", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cycles", type=int, default=5)
    args = ap.parse_args()

    import torch
    assert torch.cuda.is_available() and torch.version.hip, "requires ROCm GPU"
    rows: list[dict] = []

    def rec(cycle: int, stage: str, extra: dict | None = None):
        r = {"cycle": cycle, "stage": stage, "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        r.update(snapshot())
        if extra:
            r.update(extra)
        rows.append(r)
        print(f"[cycle {cycle}] {stage}: alloc={r['torch_memory_allocated']} "
              f"reserved={r['torch_memory_reserved']} vram={r['rocm_vram_used']} "
              f"gtt={r['rocm_gtt_used']} rss={r['host_rss']}", flush=True)

    from yue2 import YuE2Pipeline
    from yue2.protocol import Sampling
    short_sampling = Sampling(max_tokens=300)

    for cycle in range(1, args.cycles + 1):
        pipe = None
        try:
            rec(cycle, "before_load")
            t0 = time.monotonic()
            pipe = YuE2Pipeline.from_pretrained(
                args.model, vae=args.vae, backend="torch-eager",
                device="cuda:0", memory_budget_gib=24)
            rec(cycle, "after_load", {"load_s": round(time.monotonic() - t0, 1)})
            t0 = time.monotonic()
            plan = pipe.plan(style="[Tags]\nsoft pop\n",
                             lyrics="[Lyrics]\nA tiny phrase.\n",
                             seed=700000 + cycle, cot="full")
            semantic = pipe.generate_semantic(plan, sampling=short_sampling)
            latents = pipe.synthesize(semantic)
            audio = pipe.decode(latents)
            rec(cycle, "after_generate",
                {"generate_s": round(time.monotonic() - t0, 1),
                 "audio_samples": len(audio) if hasattr(audio, "__len__") else None})
        finally:
            if pipe is not None:
                t0 = time.monotonic()
                pipe.close()
                rec(cycle, "after_close", {"close_s": round(time.monotonic() - t0, 1)})
            del pipe
            gc.collect()
            rec(cycle, "after_gc")
            torch.cuda.empty_cache()
            rec(cycle, "after_empty_cache")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list = []
    for r in rows:  # union: extra stage keys (load_s/generate_s/close_s) vary per row
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"MEMORY LIFECYCLE DONE: {len(rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
