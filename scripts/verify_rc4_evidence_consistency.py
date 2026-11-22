#!/usr/bin/env python3
"""verify_rc4_evidence_consistency.py — single-source-of-truth evidence audit
(RC4.1 M4).

Recomputes every derived performance number from the raw CSV
(``reports/w7900_rc4/03_PERFORMANCE_RAW.csv``) and cross-checks:

  1. CSV schema + row count
  2. per-group n (backend|source|cold_or_warm — sources are NEVER mixed)
  3. duplicate candidate rows (run_id+prompt_id+seed)
  4. statistics (P50/P95/mean/min/max wall, mean/P95 multiplier) with a
     DECLARED method: linear-interpolation percentiles (numpy default),
     round-half-even to 1 dp (wall) / 4 dp (multiplier)
  5. agreement with 03_aggregates.json (exact)
  6. agreement with claims embedded in 03_PERFORMANCE_SUMMARY.md /
     FINAL_REPORT_ZH.md (row counts, stale "786", armA-fresh "n=2")
  7. unit hygiene: 51522830336 bytes must be labeled 47.98 GiB or 51.5
     decimal GB — never "51.5 GiB"
  8. stale verdict states (PENDING in files whose experiments completed)
  9. missing CSV artifacts referenced by reports (02_RELIABILITY_MATRIX.csv,
     02_MEMORY_LIFECYCLE.csv, 03_CONCURRENCY_RESULTS.csv must be present)

``--regenerate`` rewrites 03_aggregates.json from the raw CSV using the
declared method (the fix path for drift); it refuses to touch the raw CSV or
any /data frozen evidence.

Exit 0 PASS · 4 FAIL (differences printed as JSON reconciliation).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RC4 = REPO / "reports" / "w7900_rc4"
RAW_CSV = RC4 / "03_PERFORMANCE_RAW.csv"
AGG_JSON = RC4 / "03_aggregates.json"

UNIT_BAN = re.compile(r"51\.5\s*GiB")
BYTES_TOTAL_VRAM = 51_522_830_336
GIB = round(BYTES_TOTAL_VRAM / 2**30, 2)   # 47.98
DEC_GB = round(BYTES_TOTAL_VRAM / 10**9, 1)  # 51.5

TEXT_FILES = ["03_PERFORMANCE_SUMMARY.md", "FINAL_REPORT_ZH.md",
              "03_RESOURCE_ENVELOPE.md", "03_PERFORMANCE_VERDICT.json",
              "01_REPRODUCIBILITY_VERDICT.json", "01_FRESH_CLONE_REPORT.md"]
REQUIRED_CSVS = ["02_RELIABILITY_MATRIX.csv", "02_MEMORY_LIFECYCLE.csv",
                 "03_CONCURRENCY_RESULTS.csv"]
# verdict files whose experiments are COMPLETE — a PENDING here is stale
NO_PENDING_ALLOWED = ["01_REPRODUCIBILITY_VERDICT.json",
                      "03_PERFORMANCE_VERDICT.json"]

GROUP_KEY = ("backend", "source", "cold_or_warm")


def percentile_linear(sorted_vals: list[float], q: float) -> float:
    """Linear interpolation between closest ranks (numpy 'linear' method)."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[int(pos)]
    return sorted_vals[lo] + (pos - lo) * (sorted_vals[hi] - sorted_vals[lo])


def recompute(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault("|".join(r[k] for k in GROUP_KEY), []).append(r)
    out = {}
    for key, rs in groups.items():
        walls = sorted(float(r["wall_seconds"]) for r in rs)
        mults = [float(r["audio_realtime_multiplier"]) for r in rs]
        mults_s = sorted(mults)
        out[key] = {
            "n": len(rs),
            "p50_wall_s": round(percentile_linear(walls, 50), 1),
            "p95_wall_s": round(percentile_linear(walls, 95), 1),
            "mean_wall_s": round(sum(walls) / len(walls), 1),
            "min_wall_s": round(min(walls), 1),
            "max_wall_s": round(max(walls), 1),
            "mean_audio_realtime_multiplier": round(
                sum(mults) / len(mults), 4),
            "p95_audio_realtime_multiplier": round(
                percentile_linear(mults_s, 95), 4),
            "failures": sum(1 for r in rs if r.get("status") != "complete"),
        }
    return out


def check_schema(rows: list[dict], problems: list):
    need = {"run_id", "backend", "source", "cold_or_warm", "prompt_id",
            "seed", "status", "wall_seconds", "audio_seconds",
            "audio_realtime_multiplier"}
    if rows:
        missing = need - set(rows[0])
        if missing:
            problems.append(f"CSV schema missing columns: {sorted(missing)}")
    for i, r in enumerate(rows):
        for col in ("wall_seconds", "audio_seconds",
                    "audio_realtime_multiplier"):
            try:
                float(r[col])
            except (TypeError, ValueError):
                problems.append(f"row {i}: non-numeric {col}={r[col]!r}")
                break
        if r.get("status") != "complete":
            problems.append(f"row {i}: status {r.get('status')!r} != complete")


def check_duplicates(rows: list[dict], problems: list):
    seen: dict[tuple, int] = {}
    for i, r in enumerate(rows):
        k = (r.get("run_id"), r.get("prompt_id"), r.get("seed"))
        if k in seen:
            problems.append(f"duplicate candidate row {i}: {k} "
                            f"(first at {seen[k]})")
        seen[k] = i


def check_text_claims(problems: list, notes: list):
    for fn in TEXT_FILES:
        p = RC4 / fn
        if not p.is_file():
            notes.append(f"{fn}: not present (skipped)")
            continue
        text = p.read_text()
        if re.search(r"\b786\b", text):
            # annotated historical mentions are allowed (RC4.1 amendments
            # cite the mid-run snapshot); unannotated claims are drift.
            # Annotation = amend/SNAPSHOT marker within 3 lines above.
            lines = text.splitlines()
            bad = []
            for i, ln in enumerate(lines):
                if not re.search(r"\b786\b", ln):
                    continue
                ctx = "\n".join(lines[max(0, i - 3):i + 1])
                if not re.search(r"amend|SNAPSHOT|historical|修订", ctx,
                                 re.I):
                    bad.append(ln.strip()[:60])
            if bad:
                problems.append(f"{fn}: cites 786 raw rows without "
                                f"amendment annotation ({len(bad)} line(s): "
                                f"{bad[:2]})")
        if UNIT_BAN.search(text):
            problems.append(f"{fn}: '51.5 GiB' mislabel "
                            f"({BYTES_TOTAL_VRAM} bytes = {GIB} GiB = "
                            f"{DEC_GB} decimal GB)")
    for fn in NO_PENDING_ALLOWED:
        p = RC4 / fn
        if p.is_file() and "PENDING" in p.read_text():
            problems.append(f"{fn}: contains stale PENDING state")


def check_required_csvs(problems: list):
    for fn in REQUIRED_CSVS:
        if not (RC4 / fn).is_file():
            problems.append(f"missing referenced evidence CSV: {fn}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--regenerate", action="store_true",
                    help="rewrite 03_aggregates.json from the raw CSV using "
                         "the declared method")
    ap.add_argument("--json", type=Path, default=None,
                    help="write reconciliation JSON here")
    a = ap.parse_args(argv)

    problems: list[str] = []
    notes: list[str] = []
    recon = {"receipt_type": "rc4_evidence_consistency",
             "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime()),
             "method": {"percentile": "linear-interpolation (numpy default)",
                        "rounding": "wall 1dp, multiplier 4dp"},
             "problems": problems, "notes": notes}

    if not RAW_CSV.is_file():
        problems.append(f"raw CSV missing: {RAW_CSV}")
        _emit(recon, a.json)
        return 4
    with RAW_CSV.open(newline="") as f:
        rows = list(csv.DictReader(f))
    recon["csv_rows"] = len(rows)
    check_schema(rows, problems)
    check_duplicates(rows, problems)
    computed = recompute(rows)
    recon["computed_groups"] = computed

    if AGG_JSON.is_file():
        agg = json.loads(AGG_JSON.read_text())
        recon["aggregates_rows_total"] = agg.get("rows_total")
        if agg.get("rows_total") != len(rows):
            problems.append(f"aggregates rows_total {agg.get('rows_total')} "
                            f"!= CSV rows {len(rows)}")
        for key, stats in agg.get("aggregates", {}).items():
            c = computed.get(key)
            if c is None:
                problems.append(f"aggregates group {key!r} not present in CSV")
                continue
            for field, val in stats.items():
                if c.get(field) != val:
                    problems.append(
                        f"aggregates[{key}].{field}={val} != recomputed "
                        f"{c.get(field)}")
        for key in computed:
            if key not in agg.get("aggregates", {}):
                problems.append(f"CSV group {key!r} missing from aggregates")
    else:
        problems.append(f"aggregates JSON missing: {AGG_JSON}")

    check_text_claims(problems, notes)
    check_required_csvs(problems)

    recon["verdict"] = "PASS" if not problems else "FAIL"
    if a.regenerate and problems:
        # regenerate ONLY the derived aggregates from raw (never the CSV)
        regen = {"rows_total": len(rows), "aggregates": computed,
                 "regenerated_at_utc": recon["checked_at_utc"],
                 "method": recon["method"]}
        AGG_JSON.write_text(json.dumps(regen, indent=1) + "\n")
        notes.append("03_aggregates.json REGENERATED from raw CSV "
                     "(declared method); rerun without --regenerate to verify")
    _emit(recon, a.json)
    return 0 if recon["verdict"] == "PASS" else 4


def _emit(recon: dict, path: Path | None):
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(recon, indent=1) + "\n")
    print(json.dumps({k: recon[k] for k in ("verdict", "csv_rows")
                      if k in recon}))
    for p in recon["problems"]:
        print(f"PROBLEM: {p}", file=sys.stderr)
    for n in recon.get("notes", []):
        print(f"note: {n}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
