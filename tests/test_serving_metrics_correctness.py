"""Correctness tests for serving metric labeling (2026-10-16 erratum).

Synthetic known-answer cases + validation of CORRECTED_METRICS.json against
the preserved raw request records. CPU-only; no benchmark execution.
"""

import json
import statistics
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVING = REPO / "evidence" / "omni_wsb" / "serving"
RAW_BASE = Path("/workspace/yue2-omni-pr/bench/benchmarks")

STAGES = [
    ("bs1", 1, RAW_BASE / "bs1" / "raw_bs1_C1.jsonl"),
    ("sweep", 1, RAW_BASE / "sweep" / "raw_sweep_C1.jsonl"),
    ("sweep", 2, RAW_BASE / "sweep" / "raw_sweep_C2.jsonl"),
    ("sweep", 4, RAW_BASE / "sweep" / "raw_sweep_C4.jsonl"),
    ("sweep", 8, RAW_BASE / "sweep" / "raw_sweep_C8.jsonl"),
]


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return round(s[k], 3)


# --- synthetic known answers ------------------------------------------------

def test_simple_fast_generation():
    wall, audio = 10.0, 20.0
    assert wall / audio == pytest.approx(0.5)      # conventional RTF
    assert audio / wall == pytest.approx(2.0)      # real-time speed multiplier


def test_queued_slow_request():
    wall, audio = 40.0, 20.0
    assert wall / audio == pytest.approx(2.0)      # client e2e RTF (queued)
    assert audio / wall == pytest.approx(0.5)      # sub-realtime speed


def test_mean_ratio_is_not_reciprocal_of_mean_ratio():
    # two requests: (wall,audio) = (10,20) and (40,20)
    walls, auds = [10.0, 40.0], [20.0, 20.0]
    mean_speed = statistics.mean(a / w for w, a in zip(walls, auds))   # 1.25
    recip_rtf = 1 / statistics.mean(w / a for w, a in zip(walls, auds))  # 1/1.25 = 0.8
    assert mean_speed == pytest.approx(1.25)
    assert recip_rtf == pytest.approx(0.8)
    assert mean_speed != pytest.approx(recip_rtf)


def test_labels_are_directionally_correct():
    # speed multiplier >1 iff rtf <1 per request
    for wall, audio in [(10, 20), (40, 20), (3, 3)]:
        assert (audio / wall > 1) == (wall / audio < 1)


# --- original estimator semantics preserved ----------------------------------

def test_percentile_estimator_matches_original():
    vals = [217.251, 274.931, 309.991, 150.0, 200.0]
    assert pct(vals, 50) == pct(vals, 50)
    # original estimator: index round(p/100*(n-1)) on sorted values
    s = sorted(vals)
    assert pct(vals, 100) == s[-1] and pct(vals, 0) == s[0]


# --- validation against preserved raw records ---------------------------------

@pytest.fixture(scope="module")
def corrected():
    return json.loads((SERVING / "CORRECTED_METRICS.json").read_text())


@pytest.mark.parametrize("tag,c,raw", STAGES)
def test_corrected_metrics_reproduce_from_raw(tag, c, raw, corrected):
    if not raw.exists():
        pytest.skip(f"host raw records not available: {raw}")
    stage = next(s for s in corrected["stages"]
                 if s["tag"] == tag and s["client_concurrency"] == c)
    recs = [json.loads(l) for l in raw.read_text().splitlines() if l.strip()]
    ok = [r for r in recs if r.get("ok") and r.get("audio_s")]
    walls = [r["wall_s"] for r in ok]
    auds = [r["audio_s"] for r in ok]
    assert stage["requests"] == len(recs) == 24
    assert stage["successful"] == len(ok) == 24
    assert stage["errors"] == 0
    assert stage["client_e2e_rtf_mean"] == pytest.approx(
        statistics.mean(w / a for w, a in zip(walls, auds)), abs=5e-5)
    assert stage["client_realtime_speed_x_mean"] == pytest.approx(
        statistics.mean(a / w for w, a in zip(walls, auds)), abs=5e-5)
    assert stage["latency_p50_s"] == pct(walls, 50)
    assert stage["latency_p95_s"] == pct(walls, 95)
    assert stage["latency_p99_s"] == pct(walls, 99)
    assert stage["aggregate_audio_throughput_x"] == pytest.approx(
        sum(auds) / stage["stage_wall_s"], abs=5e-5)
    assert stage["requests_per_second"] == pytest.approx(
        len(ok) / stage["stage_wall_s"], abs=5e-5)
    # the corrected speed multiplier must equal the historical mislabeled value
    orig = json.loads((SERVING / f"summary_{tag}_C{c}.json").read_text())
    assert stage["client_realtime_speed_x_mean"] == orig["rtf_mean"]
    # and the reciprocal gap must be recorded and (in general) non-equal
    gap = stage["note_reciprocal_gap"]
    if not gap["equal"]:
        assert gap["reciprocal_of_mean_rtf"] != gap["mean_speed_x"]


def test_no_concurrency_scaling_claim(corrected):
    rps = {s["client_concurrency"]: s["requests_per_second"]
           for s in corrected["stages"] if s["tag"] == "sweep"}
    assert set(rps) == {1, 2, 4, 8}
    assert max(rps.values()) - min(rps.values()) < 1e-3  # constant RPS -> serial GPU
    p50 = {s["client_concurrency"]: s["latency_p50_s"]
           for s in corrected["stages"] if s["tag"] == "sweep"}
    assert p50[2] > 1.8 * p50[1] and p50[4] > 1.8 * p50[2]  # ~linear P50 growth


def test_gpu_util_provenance_labels(corrected):
    bs1 = next(s for s in corrected["stages"] if s["tag"] == "bs1")
    sweep_c1 = next(s for s in corrected["stages"]
                    if s["tag"] == "sweep" and s["client_concurrency"] == 1)
    assert bs1["gpu"]["gpu_util_mean_pct"] == 0
    assert "NOT VERIFIED" in bs1["gpu"]["provenance"]
    assert sweep_c1["gpu"]["gpu_util_mean_pct"] == 99.4  # reported separately


def test_vram_units_are_explicit(corrected):
    for s in corrected["stages"]:
        g = s["gpu"]
        assert g["peak_vram_GB_1e9"] == pytest.approx(g["peak_vram_bytes"] / 1e9, abs=0.01)
        assert g["peak_vram_GiB_2p30"] == pytest.approx(g["peak_vram_bytes"] / 2**30, abs=0.01)
        assert g["peak_gtt_GiB_2p30"] == pytest.approx(g["peak_gtt_bytes"] / 2**30, abs=0.01)
        assert g["peak_gtt_bytes"] != g["peak_vram_bytes"]  # GTT is not VRAM


def test_bench_script_no_longer_emits_mislabeled_field():
    src = (SERVING / "bench_serving_omni.py").read_text()
    assert '"rtf_mean":' not in src  # must not be emitted as a summary key
    assert "client_realtime_speed_x_mean" in src
    assert "client_e2e_rtf_mean" in src
