#!/usr/bin/env python3
"""rc6_q3o_comparator.py — RC6 A4.4 / B4: same-audio Q3O cross-engine
comparator (ROCm-adapted HF judge vs official CUDA vLLM judge).

Compares two Q3O run directories (each: receipts/<generation_id>/q3o.json +
identity.json + summary.json, the exact schema written by
scripts/rc5_q3o_judge.py and by the CUDA runbook's collector) over the SAME
frozen audio set. Emits: coverage, per-candidate paired differences (overall
+ every dimension), mean/median delta, agreement ladder, language/duration
strata, bootstrap CI, failure taxonomy, tie-break disclosure — and applies
ONLY pre-registered equivalence criteria (no post-hoc thresholds; without
--criteria the verdict is PENDING_CRITERIA and raw statistics only).

Self-test (no CUDA needed): --selftest runs (a) self-comparison (must be
zero-difference) and (b) a synthetic perturbation (must be detected).

Usage:
  python3 scripts/rc6_q3o_comparator.py --rocm-dir <run> --cuda-dir <run> \
      --selected-manifest reports/w7900_rc5/rc5_1/05_SELECTED_MANIFEST.json \
      [--criteria criteria.json] --out comparison.json
  python3 scripts/rc6_q3o_comparator.py --selftest --rocm-dir <run> [--out ...]
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

DIMENSIONS = ("vocal_timbre", "vocal_gender", "genre", "mood", "inst",
              "tempo", "key")


def load_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    receipts = {}
    rdir = run_dir / "receipts"
    for p in sorted(rdir.glob("*/q3o.json")):
        d = json.loads(p.read_text())
        if d.get("status") == "complete":
            receipts[d["q3o"]["generation_id"]] = d
    identity = {}
    ip = run_dir / "identity.json"
    if ip.is_file():
        identity = json.loads(ip.read_text())
    summary = {}
    sp = run_dir / "summary.json"
    if sp.is_file():
        summary = json.loads(sp.read_text())
    return {"dir": str(run_dir), "receipts": receipts, "identity": identity,
            "summary": summary}


def flat_score(d: dict) -> dict:
    q = d["q3o"]
    out = {"overall_0_5": q.get("overall_0_5"),
           "weight_sum": q.get("weight_sum"),
           "invalid_score_count": q.get("invalid_score_count")}
    for dim in DIMENSIONS:
        dd = (q.get("dimensions") or {}).get(dim) or {}
        out[f"dim.{dim}.score"] = dd.get("score")
        out[f"dim.{dim}.weight"] = dd.get("weight")
    return out


def strata_of(cid: str, lang_map: dict, dur_map: dict) -> dict:
    prompt = "_".join(cid.split("_")[:2])
    dur = dur_map.get(cid)
    tercile = None
    if dur is not None:
        tercile = "short" if dur < 210 else ("mid" if dur < 260 else "long")
    return {"lang": lang_map.get(cid), "duration_tercile": tercile,
            "prompt": prompt}


def compare(rocm: dict, cuda: dict, lang_map: dict, dur_map: dict) -> dict:
    ids = sorted(set(rocm["receipts"]) & set(cuda["receipts"]))
    rows = []
    for cid in ids:
        a, b = flat_score(rocm["receipts"][cid]), flat_score(cuda["receipts"][cid])
        diffs = {}
        for k in a:
            va, vb = a[k], b[k]
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)) \
                    and va is not None and vb is not None:
                diffs[k] = round(vb - va, 6)
            else:
                diffs[k] = 0 if va == vb else None
        rows.append({"id": cid, **strata_of(cid, lang_map, dur_map),
                     "rocm": a, "cuda": b, "delta": diffs})
    deltas = [r["delta"]["overall_0_5"] for r in rows
              if r["delta"]["overall_0_5"] is not None]
    agreement = {
        "exact": sum(1 for d in deltas if d == 0),
        "within_0_5": sum(1 for d in deltas if abs(d) <= 0.5),
        "within_1_0": sum(1 for d in deltas if abs(d) <= 1.0),
        "gt_1_0": sum(1 for d in deltas if abs(d) > 1.0),
    }
    by_stratum = {}
    for key in ("lang", "duration_tercile"):
        for val in sorted({r[key] for r in rows} - {None}):
            ds = [r["delta"]["overall_0_5"] for r in rows
                  if r[key] == val and r["delta"]["overall_0_5"] is not None]
            by_stratum[f"{key}:{val}"] = {
                "n": len(ds), "mean_delta": round(sum(ds) / len(ds), 6) if ds else None,
                "mean_rocm": round(sum(r["rocm"]["overall_0_5"] for r in rows
                                       if r[key] == val) / len(ds), 6) if ds else None}
    # paired bootstrap on mean delta
    rng = random.Random(1234)
    stats = []
    for _ in range(10000):
        stats.append(sum(rng.choice(deltas) for _ in range(len(deltas))) / len(deltas))
    stats.sort()
    return {
        "coverage": {
            "rocm_receipts": len(rocm["receipts"]), "cuda_receipts": len(cuda["receipts"]),
            "joined": len(ids),
            "rocm_only": sorted(set(rocm["receipts"]) - set(cuda["receipts"]))[:10],
            "cuda_only": sorted(set(cuda["receipts"]) - set(rocm["receipts"]))[:10],
        },
        "judge_identity": {
            "rocm": {k: rocm["identity"].get(k) for k in
                     ("judge_source_sha256", "moe_source_sha256", "identity_sha256")},
            "cuda": {k: cuda["identity"].get(k) for k in
                     ("judge_source_sha256", "moe_source_sha256", "identity_sha256")},
            "models": {
                "rocm": next(iter({r["q3o"].get("judge_model")
                                   for r in rocm["receipts"].values()}), None),
                "cuda": next(iter({r["q3o"].get("judge_model")
                                   for r in cuda["receipts"].values()}), None),
            },
        },
        "means": {
            "rocm_overall": round(sum(r["rocm"]["overall_0_5"] for r in rows) / len(rows), 6)
            if rows else None,
            "cuda_overall": round(sum(r["cuda"]["overall_0_5"] for r in rows) / len(rows), 6)
            if rows else None,
            "mean_paired_delta": round(sum(deltas) / len(deltas), 6) if deltas else None,
            "median_paired_delta": round(sorted(deltas)[len(deltas) // 2], 6) if deltas else None,
        },
        "agreement_ladder": agreement,
        "strata": by_stratum,
        "bootstrap_95ci_mean_delta": [round(stats[int(0.025 * 10000)], 6),
                                      round(stats[int(0.975 * 10000)], 6)] if deltas else None,
        "failure_taxonomy": {
            "rocm_failed_or_missing": len(rocm["summary"].get("ids", [])) - len(rocm["receipts"])
            if rocm["summary"].get("ids") else None,
            "cuda_failed_or_missing": len(cuda["summary"].get("ids", [])) - len(cuda["receipts"])
            if cuda["summary"].get("ids") else None,
        },
        "tie_break_disclosure": "the ROCm-adapted judge pins top-k ties to the lowest expert "
                                "index (stable argsort); the official vLLM CUDA fused-MoE "
                                "kernel's tie rule is NOT published — with ~18-20% of routed "
                                "slots at exact boundary ties, per-token expert CHOICE is not "
                                "comparable; this comparison measures SCORE-level agreement",
        "paired_rows": rows,
    }


def apply_criteria(comp: dict, criteria: dict) -> dict:
    v = []
    m = comp["means"]
    ci = comp["bootstrap_95ci_mean_delta"] or [0, 0]
    for c in criteria.get("criteria", []):
        k = c["kind"]
        if k == "mean_delta_within":
            ok = m["mean_paired_delta"] is not None and \
                abs(m["mean_paired_delta"]) <= c["max_abs"]
            v.append({"criterion": c, "pass": ok})
        elif k == "ci_excludes_abs":
            ok = abs(ci[0]) >= c["min_abs"] or abs(ci[1]) >= c["min_abs"]
            v.append({"criterion": c, "pass": not ok})
        elif k == "agreement_at_least":
            ok = comp["agreement_ladder"].get(c["ladder"], 0) >= c["min_count"]
            v.append({"criterion": c, "pass": ok})
        else:
            v.append({"criterion": c, "pass": None, "note": "unknown criterion kind"})
    overall = all(x["pass"] for x in v if x["pass"] is not None) if v else None
    return {"criteria_results": v, "overall": overall,
            "verdict": "EQUIVALENT_UNDER_PREREGISTERED_CRITERIA" if overall else
                       ("NOT_EQUIVALENT_UNDER_PREREGISTERED_CRITERIA" if overall is False
                        else "PENDING_CRITERIA")}


def selftest(rocm_dir: Path, out: Path) -> int:
    rocm = load_run(rocm_dir)
    same = compare(rocm, rocm, {}, {})
    zero = (same["means"]["mean_paired_delta"] == 0.0 and
            same["agreement_ladder"]["exact"] == len(same["paired_rows"]))
    # perturbation control: flip one score by +1.0
    import copy
    pert = copy.deepcopy(rocm)
    cid = sorted(pert["receipts"])[0]
    pert["receipts"][cid]["q3o"]["overall_0_5"] = \
        pert["receipts"][cid]["q3o"]["overall_0_5"] + 1.0
    diff = compare(rocm, pert, {}, {})
    detected = (diff["means"]["mean_paired_delta"] > 0 and
                diff["agreement_ladder"]["exact"] < len(diff["paired_rows"]))
    result = {
        "schema": "yue2-rc6-q3o-comparator-selftest/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "self_comparison_zero": zero,
        "perturbation_detected": detected,
        "n_receipts": len(rocm["receipts"]),
        "verdict": "PASS" if (zero and detected) else "FAIL",
    }
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result))
    return 0 if result["verdict"] == "PASS" else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rocm-dir", type=Path)
    ap.add_argument("--cuda-dir", type=Path)
    ap.add_argument("--selected-manifest", type=Path)
    ap.add_argument("--criteria", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest(a.rocm_dir, a.out)
    if not (a.rocm_dir and a.cuda_dir):
        ap.error("--rocm-dir and --cuda-dir required (or --selftest)")
    lang_map, dur_map = {}, {}
    if a.selected_manifest and a.selected_manifest.is_file():
        doc = json.loads(a.selected_manifest.read_text())
        cands = doc.get("candidates") or doc.get("selected") or []
        for c in cands:
            lang_map[c["id"]] = c.get("lang")
            dur_map[c["id"]] = c.get("audio_seconds")
    comp = compare(load_run(a.rocm_dir), load_run(a.cuda_dir), lang_map, dur_map)
    comp["schema"] = "yue2-rc6-q3o-comparison/1"
    comp["generated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    comp["rocm_dir"], comp["cuda_dir"] = str(a.rocm_dir), str(a.cuda_dir)
    comp["audio_identity_note"] = ("join key = generation_id; the runbook requires BOTH sides "
                                   "to hash the same frozen audio set (audio_sha256 manifest) "
                                   "before judging — same FLAC/MP3 identity, not just same ids")
    if a.criteria:
        comp["equivalence"] = apply_criteria(comp, json.loads(a.criteria.read_text()))
    else:
        comp["equivalence"] = {"verdict": "PENDING_CRITERIA",
                               "note": "no pre-registered criteria supplied; raw statistics "
                                       "only — thresholds must be fixed by the protocol owner "
                                       "BEFORE the CUDA run (never post-hoc)"}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(comp, indent=1) + "\n")
    slim = {k: comp[k] for k in ("schema", "coverage", "means", "agreement_ladder",
                                 "strata", "bootstrap_95ci_mean_delta", "equivalence")}
    print(json.dumps(slim, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
