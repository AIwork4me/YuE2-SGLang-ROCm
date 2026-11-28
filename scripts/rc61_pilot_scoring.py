#!/usr/bin/env python3
"""rc61_pilot_scoring.py — M5.4: five-metric scoring for the fresh-clone
benchmark pilot (10 candidates, indices 0,1,2,79,81 x 2).

Default developer path = the CORRECTED vLLM PER arm (Scoreboard B lineage):

  1. SongBench / MuLan / AllMusicCaps via the frozen official evaluator
     (rc6_corrected_scoreboard_driver on the pilot's evaluation_inputs.jsonl)
  2. PER via rc5_asr_vllm_native.py (vLLM 0.19.1 ROCm) + rc5_score_transcripts
     (official scorer) over the pilot audio manifest
  3. Official best-of-2 PER selection (min (per, edits, abs phoneme diff,
     candidate_index) per prompt) -> 5 selected candidates
  4. Q3O via rc5_q3o_judge.py on the selected 5 (frozen judge, GPU lock held
     by the caller)
  5. Unified <run>/scoring/summary.json (five_metric) for rc6_verify_results

Usage (GPU lock held by the caller):
  python3 scripts/rc61_pilot_scoring.py --run-dir <pilot run dir> \
      --workspace /data/yue2-rc6_1-fresh/workspace
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run(cmd: list[str], env: dict | None = None, log=print) -> int:
    import os
    e = dict(os.environ)
    if env:
        e.update({k: str(v) for k, v in env.items()})
    printable = " ".join(str(c) for c in cmd[:8])
    log(f"[pilot-scoring] $ {printable} ...")
    p = subprocess.run([str(c) for c in cmd], env=e)
    return p.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--skip-q3o", action="store_true")
    a = ap.parse_args()
    W = a.workspace
    run = a.run_dir.resolve()
    ev_inputs = run / "evaluation_inputs.jsonl"
    if not ev_inputs.is_file():
        print(f"FATAL: no evaluation_inputs.jsonl under {run}")
        return 2
    ws_eval_root = W / "benchmark" / "wsb_metrics"
    py_eval = W / "environments" / "yue2-gfx1100" / "bin" / "python"
    py_vllm = W / "environments" / "vllm-rocm" / "bin" / "python"
    report = run / "scoring"
    report.mkdir(parents=True, exist_ok=True)
    steps = []

    def step(name, rc, detail=""):
        steps.append({"step": name, "rc": rc, "detail": str(detail)[:200]})
        print(f"[pilot-scoring] {name}: rc={rc}")
        return rc

    # ---- 1) SongBench / MuLan / AllMusicCaps (official evaluator) ----
    rc = step("songbench+mulan+allmusiccaps (official evaluator)",
              run([sys.executable, str(REPO / "scripts" / "rc6_corrected_scoreboard_driver.py"),
                   "--evaluator-root", str(ws_eval_root), "--input", str(ev_inputs),
                   "--report", str(report), "--metrics", "songbench,mulan,allmusiccaps"],
                  env={"YUE2_WORKSPACE": str(W)}))
    if rc != 0:
        return rc

    # ---- 2) audio manifest for the ASR arm (from the prepared rows) ----
    rows = [json.loads(l) for l in (report / "audio_manifest.jsonl").read_text().splitlines()
            if l.strip()] if (report / "audio_manifest.jsonl").is_file() else []
    if not rows:
        # the driver's summary carries the full row set via prepare_inputs;
        # rebuild the manifest from the report's receipt identities + mp3s
        import hashlib

        def sha(p: Path) -> str:
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(4 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()
        rows = []
        for entry in [json.loads(l) for l in ev_inputs.read_text().splitlines() if l.strip()]:
            cid = f"wsb_{entry['prompt_index']:03d}_r{entry['candidate_index']}_s{entry['seed']}"
            mp3 = report / "audio" / cid / "audio.mp3"
            if not mp3.is_file():
                print(f"FATAL: expected prepared audio missing: {mp3}")
                return 2
            rows.append({**entry, "id": cid, "audio_path": str(mp3),
                         "audio_sha256": sha(mp3)})
        (report / "audio_manifest.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    # ---- 3) PER: vLLM ASR (corrected arm) + official scorer ----
    transcripts = report / "per_transcripts.jsonl"
    rc = step("PER ASR (vLLM corrected arm)",
              run([str(py_vllm), str(REPO / "scripts" / "rc5_asr_vllm_native.py"),
                   "--asr-root", str(W / "models" / "Qwen3-ASR-1.7B"),
                   "--manifest", str(report / "audio_manifest.jsonl"),
                   "--out", str(transcripts), "--repeats", "4"],
                  env={"YUE2_WORKSPACE": str(W)}))
    if rc != 0:
        return rc
    per_rows = report / "per_rows.jsonl"
    rc = step("PER scoring (official phoneme scorer)",
              run([str(py_eval), str(REPO / "scripts" / "rc5_score_transcripts.py"),
                   "--evaluator-root", str(ws_eval_root),
                   "--manifest", str(report / "audio_manifest.jsonl"),
                   "--transcripts", str(transcripts), "--out", str(per_rows),
                   "--engine-label", "E2 vLLM 0.19.1 native (pilot)",
                   "--expected-repeats", "4"],
                  env={"YUE2_WORKSPACE": str(W)}))
    if rc != 0:
        return rc

    # ---- 4) official best-of-2 selection ----
    per = [json.loads(l) for l in per_rows.read_text().splitlines() if l.strip()]
    by_prompt: dict[int, list] = {}
    for r in per:
        by_prompt.setdefault(r["prompt_index"], []).append(r)
    selected = []
    for p, cands in sorted(by_prompt.items()):
        def key(r):
            return (r["per"], r["edits"],
                    abs(r["reference_phonemes"] - r.get("hypothesis_phonemes", r["reference_phonemes"])),
                    r["candidate_index"])
        best = min(cands, key=key)
        selected.append({"id": best["id"], "prompt_index": p,
                         "candidate_index": best["candidate_index"],
                         "per": best["per"], "edits": best["edits"],
                         "reference_phonemes": best["reference_phonemes"]})
    sel_manifest = report / "pilot_selection.json"
    sel_manifest.write_text(json.dumps({
        "schema": "yue2-rc6_1-pilot-selection/1",
        "selection": "official wsb_eval select_candidates ordering key: "
                     "min (per, edits, abs phoneme diff, candidate_index) per prompt",
        "candidates": selected}, indent=1, ensure_ascii=False) + "\n")

    # ---- 5) Q3O on the selected 5 ----
    q3o_scores = None
    if not a.skip_q3o:
        q3o_rows = []
        for s in selected:
            row = next(r for r in rows if r["id"] == s["id"])
            q3o_rows.append(row)
        q3o_input = report / "q3o_input.jsonl"
        q3o_input.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                     for r in q3o_rows))
        q3o_out = report / "q3o"
        rc = step("Q3O (frozen judge, 5 selected)",
                  run([str(py_vllm), str(REPO / "scripts" / "rc5_q3o_judge.py"),
                       "--evaluator-root", str(ws_eval_root),
                       "--rows", str(q3o_input), "--out", str(q3o_out),
                       "--gpu-layers", "34"],
                      env={"YUE2_WORKSPACE": str(W)}))
        if rc != 0:
            return rc
        q3o_summary = json.loads((q3o_out / "summary.json").read_text())
        q3o_scores = q3o_summary.get("q3o_mean_0_5")

    # ---- 6) unified five-metric summary for the verifier ----
    summary_selv = json.loads((report / "summary_selv.json").read_text())
    g = summary_selv.get("groups", {}).get("all", {})
    sb = (g.get("songbench") or {}).get("means", {}).get("Global Avg")
    mulan = (g.get("mulan") or {}).get("means", {}).get("mulan")
    amc = (g.get("allmusiccaps") or {}).get("means", {}).get("allmusiccaps")
    per_mean = sum(r["edits"] for r in per) / sum(r["reference_phonemes"] for r in per)
    per_sel = sum(s["edits"] for s in selected) / sum(s["reference_phonemes"] for s in selected)
    five = {
        "songbench": round(sb, 6) if sb is not None else None,
        "per": round(per_sel, 6),
        "mulan": round(mulan, 6) if mulan is not None else None,
        "allmusiccaps": round(amc, 6) if amc is not None else None,
        "q3o": q3o_scores,
    }
    cov = {
        "songbench": (g.get("songbench") or {}).get("scored"),
        "per": len(selected),
        "mulan": (g.get("mulan") or {}).get("scored"),
        "allmusiccaps": (g.get("allmusiccaps") or {}).get("scored"),
        "q3o": len(selected) if q3o_scores is not None else None,
    }
    out = {
        "schema": "yue2-rc6_1-pilot-scoring/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_dir": str(run),
        "arm": "corrected vLLM PER developer path (Scoreboard B lineage)",
        "five_metric": five, "coverage": cov,
        "per_micro_all_10": round(per_mean, 6),
        "per_micro_selected_5": round(per_sel, 6),
        "selection_manifest": str(sel_manifest),
        "steps": steps,
        "scope": "PILOT (10 candidates; 5 selected) — never compared with the "
                 "full selected-192 scoreboard as a quality claim",
    }
    (report / "summary.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(five, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
