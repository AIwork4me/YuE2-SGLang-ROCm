#!/usr/bin/env python3
"""rc61_q3o_repeatability.py — M4.5: Q3O repeatability audit on a frozen
representative subset of the corrected selection.

Subset selection criteria (frozen BEFORE any scoring — no cherry-picking):
  zh + en candidates, short + long audio, previously-low + previously-high
  Q3O, high MoE routing tie counts. 8 candidates, deterministic pick.

Each candidate is scored TWICE in ONE process (judge --repeat 2 keeps
q3o.run-01/02.json) and the whole subset ONCE MORE in a SECOND independent
process (separate model load) — distinguishing intra-process repeatability
from cross-process determinism.

Usage (GPU lock held by the caller):
  python3 scripts/rc61_q3o_repeatability.py --out /data/yue2-runs/rc6_1-q3o-repeat [--venv PY]
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))


def pick_subset(entries: list[dict], numeric: dict[str, dict]) -> list[str]:
    """Deterministic frozen-subset pick: 8 candidates covering the audit
    dimensions (lang mix, audio length extremes, score extremes, tie-rich)."""
    rows = []
    for e in entries:
        n = numeric.get(e["id"], {})
        rows.append({
            "id": e["id"], "lang": e["lang"],
            "q3o": n.get("q3o_0_5"),
            "ties": (n.get("routing_tie_stats") or {}).get("tied_gates") or 0,
            "tokens": n.get("generated_tokens") or 0,
            "audio_hint": e.get("audio_seconds_hint"),
        })
    scored = [r for r in rows if r["q3o"] is not None]
    zh = sorted([r for r in scored if r["lang"] == "zh"], key=lambda r: r["id"])
    en = sorted([r for r in scored if r["lang"] != "zh"], key=lambda r: r["id"])
    by_score = sorted(scored, key=lambda r: (r["q3o"], r["id"]))
    by_ties = sorted(scored, key=lambda r: (-r["ties"], r["id"]))
    picked = []
    def add(r):
        if r and r["id"] not in [x["id"] for x in picked]:
            picked.append(r)
    add(by_score[0]); add(by_score[-1])          # previously low / high Q3O
    add(zh[0] if zh else None); add(en[0] if en else None)   # lang mix
    add(by_ties[0]); add(by_ties[1])             # tie-rich routing
    add(zh[-1] if len(zh) > 1 else by_score[len(by_score) // 2])
    add(en[-1] if len(en) > 1 else by_score[(len(by_score) * 2) // 3])
    while len(picked) < 8 and by_score:
        add(by_score[len(picked) % len(by_score)])
    return [r["id"] for r in picked[:8]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--venv", default="/data/yue2/environments/vllm-rocm/bin/python")
    a = ap.parse_args()
    out = a.out
    sel = json.loads((REPO / "reports/developer_reference/rc6_1" /
                      "04_Q3O_CORRECTED_SELECTION_MANIFEST.json").read_text())
    entries = sel["candidates"]
    numeric = {}
    num_path = REPO / "reports/developer_reference/rc6_1/04_Q3O_NUMERIC_RECEIPTS.jsonl"
    if num_path.is_file():
        numeric = {json.loads(l)["id"]: json.loads(l)
                   for l in num_path.read_text().splitlines() if l.strip()}
    subset = pick_subset(entries, numeric)
    print(f"[repeat] frozen subset ({len(subset)}): {subset}")

    rows = []
    for cid in subset:
        e = next(x for x in entries if x["id"] == cid)
        rows.append(e)
    out.mkdir(parents=True, exist_ok=True)
    (out / "q3o_input.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (out / "subset.json").write_text(json.dumps({
        "ids": subset,
        "selection_criteria": "frozen deterministic pick: lang mix, Q3O extremes, "
                              "tie-rich routing, long/short — chosen BEFORE any "
                              "repeat scoring",
    }, indent=1) + "\n")

    t0 = time.time()
    # process 1: two repeats per candidate in one process
    p1 = subprocess.run([a.venv, str(REPO / "scripts" / "rc5_q3o_judge.py"),
                         "--evaluator-root", "/data/yue2/benchmark/wsb_metrics",
                         "--rows", str(out / "q3o_input.jsonl"),
                         "--out", str(out), "--gpu-layers", "34", "--repeat", "2"])
    print(f"[repeat] process 1 rc={p1.returncode} ({time.time()-t0:.0f}s)")
    if p1.returncode != 0:
        return p1.returncode

    # process 2: independent process, fresh model load, single scoring
    out2 = out.parent / (out.name + "-proc2")
    out2.mkdir(parents=True, exist_ok=True)
    t1 = time.time()
    p2 = subprocess.run([a.venv, str(REPO / "scripts" / "rc5_q3o_judge.py"),
                         "--evaluator-root", "/data/yue2/benchmark/wsb_metrics",
                         "--rows", str(out / "q3o_input.jsonl"),
                         "--out", str(out2), "--gpu-layers", "34"])
    print(f"[repeat] process 2 rc={p2.returncode} ({time.time()-t1:.0f}s)")
    if p2.returncode != 0:
        return p2.returncode

    # analysis
    report = {"schema": "yue2-rc6_1-q3o-repeatability/1",
              "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "subset": subset, "rows": []}
    all_ok = True
    for cid in subset:
        r1 = json.loads((out / "receipts" / cid / "q3o.run-01.json").read_text())
        r2 = json.loads((out / "receipts" / cid / "q3o.run-02.json").read_text())
        r3 = json.loads((out2 / "receipts" / cid / "q3o.json").read_text())
        toks = [((r.get("raw_decode") or [{}])[-1] or {}).get("generated_token_ids_sha256")
                for r in (r1, r2, r3)]
        scores = [(r.get("scores") or {}).get("q3o") for r in (r1, r2, r3)]
        intra = toks[0] == toks[1] and scores[0] == scores[1]
        cross = toks[1] == toks[2] and scores[1] == scores[2]
        row = {"id": cid, "scores": scores,
               "token_identity_intra_process": bool(intra),
               "token_identity_cross_process": bool(cross),
               "score_variance": statistics.pvariance([s for s in scores
                                                       if s is not None]) if scores else None,
               "routing_ties": [r.get("routing_tie_stats") for r in (r1, r2, r3)]}
        report["rows"].append(row)
        all_ok = all_ok and intra and cross
    report["verdicts"] = {
        "INTRA_ENGINE_REPEATABILITY": "IDENTICAL" if all(
        r["token_identity_intra_process"] and r["score_variance"] == 0
        for r in report["rows"]) else "DIVERGED",
        "CROSS_PROCESS_DETERMINISM": "IDENTICAL" if all(
        r["token_identity_cross_process"] for r in report["rows"]) else "DIVERGED",
        "CROSS_IMPLEMENTATION_NUMERICAL_EQUIVALENCE": "NOT_TESTED_HERE (same "
        "implementation, different processes; official CUDA engine comparison "
        "remains NOT_ESTABLISHED)",
    }
    report["verdict"] = "PASS" if all_ok else "DIVERGED"
    dest = REPO / "reports/developer_reference/rc6_1/04_Q3O_REPEATABILITY.json"
    dest.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(report["verdicts"], indent=1))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
