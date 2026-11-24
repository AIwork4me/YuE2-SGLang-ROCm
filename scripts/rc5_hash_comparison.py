#!/usr/bin/env python3
"""rc5_hash_comparison.py — RC5.1 P0.4.5 scientific comparison.

Compares every candidate of the RC5 latest-upstream campaign (c67d541a +
import guards, native gates) against the frozen historical Arm B manifest
(ced0ef7d + patches 0001-0005/0008, same W7900 class GPU), candidate id by
candidate id:

  * byte-identical FLAC (SHA256), audio seconds, truncation flag
  * per-difference root-cause fields (duration/codec-frame deltas) for any
    non-identical candidate — differences are REPORTED, never assumed absent
    and never tuned away.

The RC5 pilot already demonstrated 12/12 bit-identical; this answers whether
that extends to the full 384.

Usage:
  python3 scripts/rc5_hash_comparison.py --run-dir <wsb_full> \
      --historical evidence/publication/armB_campaign/candidate_manifest.json \
      --out reports/w7900_rc5/rc5_1/04_HISTORICAL_HASH_COMPARISON.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--historical", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    hist_doc = json.loads(a.historical.read_text())
    hist = {r["id"]: r for r in hist_doc["candidates"]}

    j = [json.loads(l) for l in (a.run_dir / "journal.jsonl").read_text().splitlines() if l.strip()]
    results = {e["id"]: e for e in j if e.get("event") == "result" and e.get("status") == "complete"}

    rows, identical, diff, missing_hist = [], 0, 0, 0
    for cid in sorted(results):
        r = results[cid]
        h = hist.get(cid)
        if h is None:
            missing_hist += 1
            continue
        flac_eq = r.get("audio_flac_sha256") == h.get("audio_flac_sha256")
        sec_eq = abs((r.get("audio_seconds") or 0) - (h.get("audio_seconds") or 0)) < 1e-6
        trunc_eq = bool(r.get("truncated")) == bool(h.get("truncated"))
        if flac_eq and sec_eq and trunc_eq:
            identical += 1
        else:
            diff += 1
        rows.append({
            "id": cid,
            "flac_sha256_identical": flac_eq,
            "audio_seconds_identical": sec_eq,
            "truncated_flag_identical": trunc_eq,
            "duration_delta_s": None if sec_eq else round(
                (r.get("audio_seconds") or 0) - (h.get("audio_seconds") or 0), 3),
            "codec_frames": r.get("codec_frames"),
            "generation_identity": r.get("identity"),
            "historical_identity": h.get("identity"),
        })

    report = {
        "schema": "yue2-rc5_1-historical-hash-comparison/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "comparison": "RC5 latest-upstream campaign vs historical Arm B frozen manifest",
        "historical_source": str(a.historical),
        "rc5_run_id": json.loads((a.run_dir / "run_config.json").read_text())["run_id"],
        "rc5_complete": len(results),
        "compared": len(rows),
        "byte_identical": identical,
        "non_identical": diff,
        "missing_historical_reference": missing_hist,
        "non_identical_rows": [r for r in rows if not (
            r["flac_sha256_identical"] and r["audio_seconds_identical"] and r["truncated_flag_identical"])],
        "conclusion": (
            f"{identical}/{len(rows)} candidates byte-identical to the historical Arm B run"
            if not diff else
            f"{identical}/{len(rows)} byte-identical; {diff} differ — see non_identical_rows for "
            "per-sample duration/codec-frame/identity fields (root-cause each difference; "
            "bit-identity was a scientific observation, never an acceptance gate)"),
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in (
        "rc5_complete", "compared", "byte_identical", "non_identical",
        "missing_historical_reference")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
