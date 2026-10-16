#!/usr/bin/env python3
"""Recompute correctly-labeled serving metrics from preserved raw request records.

Correction context (2026-10-16 erratum):
  The original bench_serving_omni.py emitted `rtf_mean = mean(audio_s/wall_s)`.
  That quantity is the per-request REAL-TIME GENERATION SPEED MULTIPLIER
  (higher = faster), NOT conventional RTF. Conventional RTF is
  wall/audio (lower = better). These are different statistics and neither is
  the reciprocal of the other's mean (Jensen gap).

Definitions used here (explicit; per successful request i):
  client_e2e_rtf_i        = wall_i / audio_i     (includes queueing for C>1)
  client_realtime_speed_i = audio_i / wall_i     (multiplier, "x")
Stage-level:
  stage_wall_s            = harness stage wall (unchanged historical value)
  requests_per_second     = successful_requests / stage_wall_s
  aggregate_audio_throughput_x = sum(audio_i) / stage_wall_s
Percentiles: original estimator kept (sorted order statistic at index
  round(p/100*(n-1)) on per-request wall seconds).

NO benchmark was re-run. Inputs are the original raw_*.jsonl files, hash-pinned.
"""

import hashlib
import json
import statistics
from pathlib import Path

RAW_BASE = Path("/workspace/yue2-omni-pr/bench/benchmarks")
EVID_SERVING = Path(__file__).resolve().parent
SCRIPT_VERSION = "correct_metrics_v2_2026-10-16"

STAGES = [
    ("bs1", 1, RAW_BASE / "bs1" / "raw_bs1_C1.jsonl"),
    ("sweep", 1, RAW_BASE / "sweep" / "raw_sweep_C1.jsonl"),
    ("sweep", 2, RAW_BASE / "sweep" / "raw_sweep_C2.jsonl"),
    ("sweep", 4, RAW_BASE / "sweep" / "raw_sweep_C4.jsonl"),
    ("sweep", 8, RAW_BASE / "sweep" / "raw_sweep_C8.jsonl"),
]

# Original percentile estimator (kept verbatim for comparability).
def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return round(s[k], 3)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    out = {"schema": 2, "generated": "2026-10-16", "script": SCRIPT_VERSION,
           "erratum": "Historical summary files' rtf_mean was mean(audio/wall) = "
                      "real-time speed multiplier (x), not RTF. Values unchanged; "
                      "labels corrected here. See "
                      "reports/final_acceptance/SERVING_PERFORMANCE_CORRECTION.md.",
           "estimator": "percentile = sorted order statistic at index round(p/100*(n-1)) "
                        "(original bench_serving_omni.py estimator, unchanged)",
           "stages": []}

    for tag, c, raw in STAGES:
        orig = json.loads((EVID_SERVING / f"summary_{tag}_C{c}.json").read_text())
        recs = [json.loads(l) for l in raw.read_text().splitlines() if l.strip()]
        ok = [r for r in recs if r.get("ok") and r.get("audio_s")]
        n_ok, n_err = len(ok), len(recs) - len(ok)
        walls = [r["wall_s"] for r in ok]
        auds = [r["audio_s"] for r in ok]
        e2e_rtf = [w / a for w, a in zip(walls, auds)]
        speed_x = [a / w for w, a in zip(walls, auds)]
        stage_wall = orig["wall_s"]  # harness stage wall (historical, unchanged)

        stage = {
            "tag": tag, "client_concurrency": c,
            "raw_input": str(raw), "raw_input_sha256": sha256(raw),
            "requests": len(recs), "successful": n_ok, "errors": n_err,
            "stage_wall_s": stage_wall,
            "requests_per_second": round(n_ok / stage_wall, 4),
            "latency_p50_s": pct(walls, 50), "latency_p95_s": pct(walls, 95),
            "latency_p99_s": pct(walls, 99),
            "latency_mean_s": round(statistics.mean(walls), 3),
            "client_e2e_rtf_mean": round(statistics.mean(e2e_rtf), 4),
            "client_e2e_rtf_p50": pct(e2e_rtf, 50),
            "client_realtime_speed_x_mean": round(statistics.mean(speed_x), 4),
            "aggregate_audio_throughput_x": round(sum(auds) / stage_wall, 4),
            "audio_s_total": round(sum(auds), 3),
            "audio_s_mean": round(statistics.mean(auds), 3),
            "note_reciprocal_gap": {
                "reciprocal_of_mean_rtf": round(1 / statistics.mean(e2e_rtf), 4),
                "mean_speed_x": round(statistics.mean(speed_x), 4),
                "equal": abs(1 / statistics.mean(e2e_rtf) - statistics.mean(speed_x)) < 5e-5,
            },
            "gpu": {
                "gpu_util_mean_pct": orig["gpu_util_mean_pct"],
                "gpu_util_p90_pct": orig["gpu_util_p90_pct"],
                "provenance": ("sweep stages: rocm-smi sampled every 2s during stage; "
                               "bs1 stage: samples all parsed 0 -> NOT VERIFIED, see "
                               "SERVING_PERFORMANCE_CORRECTION.md"),
                "peak_vram_bytes": orig["peak_vram_bytes"],
                "peak_vram_GB_1e9": round(orig["peak_vram_bytes"] / 1e9, 2),
                "peak_vram_GiB_2p30": round(orig["peak_vram_bytes"] / 2**30, 2),
                "peak_gtt_bytes": orig["peak_gtt_bytes"],
                "peak_gtt_GB_1e9": round(orig["peak_gtt_bytes"] / 1e9, 2),
                "peak_gtt_GiB_2p30": round(orig["peak_gtt_bytes"] / 2**30, 2),
            },
            "old_field_mapping": {
                "old_rtf_mean": orig["rtf_mean"],
                "old_rtf_mean_is_now": "client_realtime_speed_x_mean (identical value, corrected label)",
            },
            "model_math_unchanged": True,
        }
        assert stage["client_realtime_speed_x_mean"] == orig["rtf_mean"], \
            f"{tag} C{c}: recomputed speed x != old rtf_mean"
        out["stages"].append(stage)

    out["interpretation"] = {
        "concurrency_note": "C=1,2,4,8 are CLIENT concurrencies against a "
                            "single-model server; GPU execution remained serial "
                            "(requests_per_second ~constant, P50 grows ~linearly). "
                            "No GPU batching or throughput scaling is claimed.",
        "rtf_note": "client_e2e_rtf includes queueing/admission for C>1; it is an "
                    "end-to-end client-observed ratio, not isolated GPU compute RTF.",
        "units": "GB = 1e9 bytes; GiB = 2^30 bytes; GTT is system-RAM aperture "
                 "memory and is NOT VRAM.",
    }
    dst = EVID_SERVING / "CORRECTED_METRICS.json"
    dst.write_text(json.dumps(out, indent=1) + "\n")
    print("wrote", dst)
    for s in out["stages"]:
        print(f"{s['tag']:5s} C{s['client_concurrency']}: ok={s['successful']}/{s['requests']} "
              f"e2e_rtf_mean={s['client_e2e_rtf_mean']} speed_x_mean={s['client_realtime_speed_x_mean']} "
              f"(old rtf_mean={s['old_field_mapping']['old_rtf_mean']}) "
              f"agg_thr={s['aggregate_audio_throughput_x']}x rps={s['requests_per_second']} "
              f"1/mean_rtf={s['note_reciprocal_gap']['reciprocal_of_mean_rtf']}")


if __name__ == "__main__":
    main()
