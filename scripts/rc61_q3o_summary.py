#!/usr/bin/env python3
"""rc61_q3o_summary.py — M4.3/M4.6 aggregation of the corrected (S_V) Q3O arm.

Reads every receipt in the corrected run dir, verifies identity/audio
binding, and produces:
  04_Q3O_CORRECTED_FULL_SUMMARY.json     aggregate + reuse accounting
  04_Q3O_NUMERIC_RECEIPTS.jsonl          NUMERIC evidence only (no judge text —
                                         public-repo safe)

Usage:  python3 scripts/rc61_q3o_summary.py --run-dir DIR
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from rc61_q3o_corrected import sha_file  # noqa: E402

OUT_DIR = REPO / "reports/developer_reference/rc6_1"


def numeric_receipt(rec: dict, entry: dict) -> dict:
    """Numeric-only view of a Q3O receipt (no raw judge text: dimension
    reasons can quote restricted lyrics)."""
    q = rec.get("q3o") or {}
    dims = {}
    for name, node in (q.get("dimensions") or {}).items():
        if isinstance(node, dict):
            dims[name] = {"score": node.get("score"),
                          "score_for_overall": node.get("score_for_overall"),
                          "weight": node.get("weight"),
                          "invalid": node.get("invalid_score")}
    return {
        "id": rec.get("row_id") or entry["id"],
        "status": rec.get("status"),
        "q3o_0_5": (rec.get("scores") or {}).get("q3o"),
        "q3o_0_1": q.get("overall_0_1"),
        "weight_sum": q.get("weight_sum"),
        "invalid_score_count": q.get("invalid_score_count"),
        "dimensions": dims,
        "frozen_weight_identity": q.get("frozen_weight_identity") or rec.get("q3o", {}).get("frozen_weight_identity"),
        "seconds": rec.get("seconds"),
        "audio_sha256": rec.get("audio_sha256"),
        "identity_sha256": rec.get("identity_sha256"),
        "rebound": "identity_rebound" in rec,
        "audio_seconds": entry.get("audio_seconds_hint"),
        "routing_tie_stats": rec.get("routing_tie_stats"),
        "generated_tokens": ((rec.get("raw_decode") or [{}])[-1] or {}).get("generated_tokens"),
        "finish_reason": ((rec.get("raw_decode") or [{}])[-1] or {}).get("finish_reason"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    a = ap.parse_args()
    run = a.run_dir
    identity = json.loads((run / "identity.json").read_text())
    canon = identity["identity_sha256"]
    sel = json.loads((OUT_DIR / "04_Q3O_CORRECTED_SELECTION_MANIFEST.json").read_text())
    entries = {e["id"]: e for e in sel["candidates"]}
    runtime = json.loads((run / "runtime_receipt.json").read_text()) \
        if (run / "runtime_receipt.json").is_file() else {}

    rows, problems = [], []
    rebound_count = 0
    for cid, e in sorted(entries.items()):
        rp = run / "receipts" / cid / "q3o.json"
        if not rp.is_file():
            problems.append(f"{cid}: receipt missing")
            continue
        rec = json.loads(rp.read_text())
        if rec.get("status") != "complete":
            problems.append(f"{cid}: status={rec.get('status')}")
            continue
        if rec.get("identity_sha256") != canon:
            problems.append(f"{cid}: identity_sha256 mismatch")
            continue
        if rec.get("audio_sha256") != e["audio_sha256"]:
            problems.append(f"{cid}: audio binding mismatch")
            continue
        if "identity_rebound" in rec:
            rebound_count += 1
        rows.append((cid, e, rec))
    if problems:
        print(json.dumps({"FATAL": "receipt verification failed", "problems": problems[:10]}))
        return 2

    scores = [(rec.get("scores") or {}).get("q3o") for _, _, rec in rows]
    by_lang = {}
    for cid, e, rec in rows:
        by_lang.setdefault(e["lang"], []).append((rec.get("scores") or {}).get("q3o"))
    sec = [rec.get("seconds") for _, _, rec in rows if isinstance(rec.get("seconds"), (int, float))]
    newly = [rec for _, _, rec in rows if "identity_rebound" not in rec]

    mean = round(statistics.fmean(scores), 6)
    summary = {
        "schema": "yue2-rc6_1-q3o-corrected-full/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "arm": "Scoreboard B — corrected vLLM PER selection S_V, Q3O judged on the "
               "same frozen audio with the frozen official weights/prompts/parser/"
               "aggregation (ROCm-adapted HF judge; official CUDA equivalence "
               "NOT_ESTABLISHED)",
        "identity_sha256": canon,
        "judge": runtime.get("judge"),
        "placement": {k: v for k, v in (runtime.get("placement") or {}).items()
                      if k in ("gpu_moe_layers", "cpu_moe_layers", "cpu_threads",
                               "gpu_moe_mode", "attn_implementation", "dtype",
                               "transformers", "torch", "hip")},
        "coverage": {"expected": 192, "evaluated": len(rows), "valid": len(rows),
                     "failed": 0, "reused_receipts": rebound_count,
                     "newly_evaluated": len(newly)},
        "score": {
            "q3o_mean_0_5": mean,
            "q3o_mean_0_1": round(mean / 5, 6),
            "q3o_std": round(statistics.pstdev(scores), 4),
            "q3o_min": min(scores), "q3o_max": max(scores),
            "q3o_by_lang": {k: round(statistics.fmean(v), 6) for k, v in by_lang.items()},
        },
        "performance": {
            "mean_seconds_all": round(statistics.fmean(sec), 2) if sec else None,
            "total_wall_newly_evaluated_est_s": round(sum(
                r.get("seconds", 0) for r in newly), 1),
            "model_load_seconds": (runtime.get("placement") or {}).get("load_seconds"),
            "note": "incremental time covers ONLY the newly evaluated candidates; "
                    "the reused 132 receipts carry their original seconds but were "
                    "NOT re-executed this round",
        },
        "resources": runtime.get("placement", {}).get("resources") or
                     {k: v for k, v in runtime.items() if "vram" in str(k).lower() or "vmhwm" in str(k).lower()},
        "references": {
            "paper_q3o": 4.68,
            "scoreboard_A_S_T_q3o": 4.393986,
            "h800_reproduction_original_audio": 4.69,
            "h800_fresh_generation": 4.71,
        },
        "selection_effect": {
            "q3o_S_V_minus_S_T": round(mean - 4.393986, 6),
            "definition": "Q3O(S_V) - Q3O(S_T); the two selections share 132 "
                          "candidates; 60 differ per the official PER selection",
        },
        "problems": [],
    }

    num_path = OUT_DIR / "04_Q3O_NUMERIC_RECEIPTS.jsonl"
    num_path.write_text("".join(json.dumps(numeric_receipt(rec, e), ensure_ascii=False)
                                + "\n" for _, e, rec in rows))
    (OUT_DIR / "04_Q3O_CORRECTED_FULL_SUMMARY.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"mean_0_5": mean, "n": len(rows),
                      "reused": rebound_count, "newly": len(newly),
                      "selection_effect": summary["selection_effect"]["q3o_S_V_minus_S_T"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
