"""verify_rc4_evidence_consistency.py tests (RC4.1 M4.7).

Two layers:
  A) synthetic fixtures — every failure mode must FAIL loudly (mutation-style
     controls that CI can run without the real evidence tree);
  B) live check — when the repo's real RC4 evidence is present (always true
     in-repo), the auditor must PASS on a consistent tree and FAIL on each
     tampered copy.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "evcons_mod", REPO / "scripts" / "verify_rc4_evidence_consistency.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

HEADER = ["run_id", "git_sha", "backend", "gpu", "prompt_id", "seed",
          "cold_or_warm", "status", "wall_seconds", "audio_seconds",
          "audio_realtime_multiplier", "source"]
ROWS = [
    ["r1", "sha", "armB_sglang_serving", "W7900", "wsb_000", 1, "warm",
     "complete", "100.0", "50.0", "0.5", "campaign_frozen"],
    ["r1", "sha", "armB_sglang_serving", "W7900", "wsb_001", 2, "warm",
     "complete", "200.0", "80.0", "0.4", "campaign_frozen"],
    ["r1", "sha", "armB_sglang_serving", "W7900", "wsb_002", 3, "warm",
     "complete", "300.0", "90.0", "0.3", "campaign_frozen"],
    ["r2", "sha", "armA_native_torch_eager", "W7900", "wsb_000", 1, "cold",
     "complete", "600.0", "60.0", "0.1", "rc4_fresh"],
]


def make_tree(tmp_path, rows=None, aggregates=None):
    d = tmp_path / "reports" / "w7900_rc4"
    d.mkdir(parents=True)
    rows = ROWS if rows is None else rows
    with (d / "03_PERFORMANCE_RAW.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    computed = ev.recompute([dict(zip(HEADER, r)) for r in rows])
    agg = aggregates if aggregates is not None else {
        "rows_total": len(rows), "aggregates": computed}
    (d / "03_aggregates.json").write_text(json.dumps(agg))
    for fn in ev.REQUIRED_CSVS:
        (d / fn).write_text("tag,case\n")
    (d / "03_PERFORMANCE_SUMMARY.md").write_text(
        f"Raw data: `03_PERFORMANCE_RAW.csv` ({len(rows)} measured rows\n")
    (d / "FINAL_REPORT_ZH.md").write_text(f"原始数据 {len(rows)} 行\n")
    (d / "03_RESOURCE_ENVELOPE.md").write_text("47.98 GiB\n")
    (d / "03_PERFORMANCE_VERDICT.json").write_text('{"v": "PASS_FINAL"}')
    (d / "01_REPRODUCIBILITY_VERDICT.json").write_text('{"v": "PASS_FINAL"}')
    return d


def run(monkeypatch, tmp_path, rows=None, aggregates=None):
    d = make_tree(tmp_path, rows, aggregates)
    mod_root = tmp_path
    monkeypatch.setattr(ev, "RC4", d)
    monkeypatch.setattr(ev, "RAW_CSV", d / "03_PERFORMANCE_RAW.csv")
    monkeypatch.setattr(ev, "AGG_JSON", d / "03_aggregates.json")
    return ev.main([])


def test_consistent_tree_passes(monkeypatch, tmp_path):
    assert run(monkeypatch, tmp_path) == 0


def test_count_mismatch_fails(monkeypatch, tmp_path):
    assert run(monkeypatch, tmp_path, aggregates={
        "rows_total": 3,
        "aggregates": ev.recompute(
            [dict(zip(HEADER, r)) for r in ROWS])}) == 4


def test_duplicate_rows_fail(monkeypatch, tmp_path):
    rows = ROWS + [ROWS[0]]
    assert run(monkeypatch, tmp_path, rows=rows) == 4


def test_stale_aggregate_value_fails(monkeypatch, tmp_path):
    computed = ev.recompute([dict(zip(HEADER, r)) for r in ROWS])
    k = next(iter(computed))
    computed[k]["p50_wall_s"] = 0.1
    assert run(monkeypatch, tmp_path, aggregates={
        "rows_total": len(ROWS), "aggregates": computed}) == 4


def test_stale_786_claim_fails(monkeypatch, tmp_path):
    assert run(monkeypatch, tmp_path) == 0
    d = ev.RC4
    (d / "FINAL_REPORT_ZH.md").write_text("原始数据 786 行\n")
    assert ev.main([]) == 4


def test_gib_mislabel_fails(monkeypatch, tmp_path):
    assert run(monkeypatch, tmp_path) == 0
    (ev.RC4 / "03_RESOURCE_ENVELOPE.md").write_text(
        "campaign peak 51.5 GiB = card total\n")
    assert ev.main([]) == 4
    # correct forms pass
    (ev.RC4 / "03_RESOURCE_ENVELOPE.md").write_text(
        "campaign peak 51.5 decimal GB (= 47.98 GiB) = card total\n")
    assert ev.main([]) == 0


def test_stale_pending_fails(monkeypatch, tmp_path):
    assert run(monkeypatch, tmp_path) == 0
    (ev.RC4 / "01_REPRODUCIBILITY_VERDICT.json").write_text(
        '{"pilot_scoring": "PENDING_GPU_WINDOW"}')
    assert ev.main([]) == 4


def test_missing_required_csv_fails(monkeypatch, tmp_path):
    assert run(monkeypatch, tmp_path) == 0
    (ev.RC4 / "02_RELIABILITY_MATRIX.csv").unlink()
    assert ev.main([]) == 4


def test_non_complete_status_fails(monkeypatch, tmp_path):
    rows = [list(r) for r in ROWS]
    rows[0][7] = "failed"
    assert run(monkeypatch, tmp_path, rows=rows) == 4


def test_wrong_row_count_citation_fails(monkeypatch, tmp_path):
    """Mutation control M10: '791 written as another number' must FAIL."""
    assert run(monkeypatch, tmp_path) == 0
    (ev.RC4 / "FINAL_REPORT_ZH.md").write_text("原始数据 786 行\n")
    assert ev.main([]) == 4  # unannotated 786 AND missing actual count 4
    (ev.RC4 / "FINAL_REPORT_ZH.md").write_text("原始数据 5 行\n")
    assert ev.main([]) == 4  # annotated? no — and count 5 != 4 rows


def test_percentile_linear():
    assert ev.percentile_linear([1.0, 2.0], 50) == 1.5
    assert ev.percentile_linear([1.0, 2.0, 3.0, 4.0], 95) == 3.85
    assert ev.percentile_linear([5.0], 95) == 5.0


def test_real_repo_evidence_consistent():
    """Layer B: the actual in-repo evidence must audit PASS (after the RC4.1
    reconciliation this test is the CI guard against re-drift)."""
    if not (REPO / "reports" / "w7900_rc4" / "03_PERFORMANCE_RAW.csv").is_file():
        pytest.skip("real evidence tree not present")
    assert ev.main([]) == 0


def test_regenerate_rewrites_only_aggregates(monkeypatch, tmp_path):
    d = make_tree(tmp_path)
    before_csv = (d / "03_PERFORMANCE_RAW.csv").read_bytes()
    computed = ev.recompute([dict(zip(HEADER, r)) for r in ROWS])
    k = next(iter(computed))
    computed[k]["n"] = 99
    (d / "03_aggregates.json").write_text(json.dumps(
        {"rows_total": len(ROWS), "aggregates": computed}))
    monkeypatch.setattr(ev, "RC4", d)
    monkeypatch.setattr(ev, "RAW_CSV", d / "03_PERFORMANCE_RAW.csv")
    monkeypatch.setattr(ev, "AGG_JSON", d / "03_aggregates.json")
    assert ev.main([]) == 4
    assert ev.main(["--regenerate"]) == 4  # still reports the drift...
    fixed = json.loads((d / "03_aggregates.json").read_text())
    assert fixed["aggregates"][k]["n"] == 3  # ...but the file is fixed
    assert (d / "03_PERFORMANCE_RAW.csv").read_bytes() == before_csv
    assert ev.main([]) == 0  # now consistent
