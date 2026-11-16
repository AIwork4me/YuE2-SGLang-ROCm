#!/usr/bin/env python3
"""mission_chain.py — serialized GPU stage machine for the fresh-image mission.

Stages (each GPU-heavy stage runs SOLO — single-GPU policy):
  armA_campaign -> armA_audit -> armA_score_per_sb -> armA_score_mulan_amc
  -> armB_acceptance -> armB_campaign -> armB_audit -> armB_score_per_sb
  -> armB_score_mulan_amc -> done

Durable state: /data/yue2/mission_state.json. Every stage is idempotent and
re-runnable; the chain never modifies official protocol inputs. Logs under
/data/yue2/logs/. GPU exclusivity is enforced by scripts/gpu_lock.py (each
GPU stage wraps its work in the lock).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

WS = Path("/data/yue2")
RUNS = Path("/data/yue2-runs")
REPO = Path("/workspace/YuE2-SGLang-ROCm")
STATE = WS / "mission_state.json"
LOG = WS / "logs" / "mission_chain.log"
PY_A = str(WS / "environments/yue2-torch/bin/python")
PY_B = str(WS / "environments/yue2-gfx1100/bin/python")
EV_METRICS = str(WS / "benchmark/WildSongBench/wsb_metrics/.venvs/metrics/bin/python")
WSB_ROOT = WS / "benchmark/WildSongBench"

SCORE_ENV = {
    **os.environ,
    "WSB_ROCM_TORCH_OVERRIDE": "1",
    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
    "HF_HOME": str(WS / "hf-cache"),
    "TMPDIR": str(WS / "tmp"),
    "YUE2_WORKSPACE": str(WS),
}


def log(msg: str) -> None:
    line = f"{time.strftime('%F %T')} [{msg}]"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def load_state() -> dict:
    if STATE.is_file():
        return json.loads(STATE.read_text())
    return {"stage": "armA_campaign", "history": []}


def save_state(s: dict) -> None:
    s["history"] = (s.get("history") or [])[-100:] + [
        {"t": time.strftime("%F %T"), "stage": s["stage"]}]
    STATE.write_text(json.dumps(s, indent=2))


def journal_complete(run_dir: Path) -> int:
    p = run_dir / "generation_manifest.jsonl"
    if not p.is_file():
        return 0
    done = set()
    for line in p.read_text().splitlines():
        if line.strip():
            try:
                r = json.loads(line)
                if r.get("status") == "complete":
                    done.add(r["id"])
            except ValueError:
                continue
    return len(done)


def audit(run_dir: Path, mode: str = "full") -> bool:
    r = subprocess.run([PY_A, str(REPO / "scripts/verify_wsb_artifacts.py"),
                        "--runs", str(run_dir), "--mode", mode],
                       capture_output=True, text=True, timeout=7200)
    (run_dir / f"audit_chain_{int(time.time())}.log").write_text(
        r.stdout + "\n--- stderr ---\n" + r.stderr)
    return r.returncode == 0 and '"verdict": "FULL"' in r.stdout


def score(run_dir: Path, metrics: str, out_subdir: str, per_results: Path | None,
          log_name: str, wait_s: float = 7200) -> bool:
    """Run official scoring SOLO under the GPU lock.

    RCA-F5 semantics: a COMPLETE summary is never re-run; a PARTIAL output dir
    is moved aside (scores_partial_<ts>, preserved for inspection) before a
    fresh attempt — the evaluator has no resume (handoff gotcha 7) and every
    attempt's stdout/stderr is archived separately by timestamp."""
    out = run_dir / out_subdir
    if (out / "summary.json").is_file():
        try:
            s = json.loads((out / "summary.json").read_text())
            if s.get("complete") is True:
                log(f"{log_name}: already complete (summary.complete=true)")
                return True
        except Exception:
            pass
    if out.exists():
        aside = run_dir / f"{out_subdir}_partial_{time.strftime('%Y%m%dT%H%M%SZ')}"
        import shutil
        shutil.move(str(out), str(aside))
        log(f"{log_name}: moved partial output aside -> {aside.name}")
    cmd = [EV_METRICS, "wsb_metrics/wsb_eval.py", "score",
           "--input", str(run_dir / "evaluation_inputs.jsonl"),
           "--output", str(out), "--mode", "standard", "--metrics", metrics]
    if per_results is not None:
        cmd += ["--per-results", str(per_results)]
    log(f"{log_name}: launching scoring -> {out}")
    proc = subprocess.run(cmd, cwd=str(WSB_ROOT), env=SCORE_ENV,
                          capture_output=True, text=True)
    ts = int(time.time())
    (WS / "logs" / f"{log_name}_{ts}.out").write_text(
        proc.stdout[-200000:] if proc.stdout else "")
    (WS / "logs" / f"{log_name}_{ts}.err").write_text(
        proc.stderr[-200000:] if proc.stderr else "")
    log(f"{log_name}: rc={proc.returncode}")
    return proc.returncode == 0


def main() -> int:
    while True:
        s = load_state()
        stage = s["stage"]
        log(f"stage={stage}")
        if stage == "armA_campaign":
            run_dir = RUNS / "armA_wsb_full"
            n = journal_complete(run_dir)
            alive = subprocess.run(["pgrep", "-f", "run_wsb_torch.py"],
                                   capture_output=True).returncode == 0
            log(f"armA journal complete={n}/384 driver_alive={alive}")
            if n >= 384:
                s["stage"] = "armA_audit"; save_state(s)
            else:
                if not alive:
                    log("armA driver not running; (re)launching resume-safe")
                    subprocess.Popen(
                        ["setsid", "nohup", "/data/yue2/run_armA_campaign.sh"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL, start_new_session=True)
                time.sleep(600)
        elif stage == "armA_audit":
            if audit(RUNS / "armA_wsb_full"):
                s["stage"] = "armA_score_per_sb"; save_state(s)
            else:
                log("armA audit NOT FULL — blocking (manual inspection)")
                time.sleep(1800)
        elif stage == "armA_score_per_sb":
            if score(RUNS / "armA_wsb_full", "per,songbench", "scores", None,
                     "armA_score_per_sb"):
                s["stage"] = "armA_score_mulan_amc"; save_state(s)
            else:
                log("armA per+songbench scoring failed; retrying in 30min")
                time.sleep(1800)
        elif stage == "armA_score_mulan_amc":
            if score(RUNS / "armA_wsb_full", "mulan,allmusiccaps", "additional",
                     RUNS / "armA_wsb_full/scores/per_song.jsonl",
                     "armA_score_mulan_amc"):
                s["stage"] = "armB_acceptance"; save_state(s)
            else:
                time.sleep(1800)
        elif stage == "armB_acceptance":
            # server acceptance handled separately (manual/scripts) — mark and go
            s["stage"] = "armB_campaign"; save_state(s)
        elif stage == "armB_campaign":
            run_dir = RUNS / "armB_wsb_full"
            n = journal_complete(run_dir)
            alive = subprocess.run(["pgrep", "-f", "run_wsb.py"],
                                   capture_output=True).returncode == 0
            log(f"armB journal complete={n}/384 driver_alive={alive}")
            if n >= 384:
                s["stage"] = "armB_audit"; save_state(s)
            else:
                time.sleep(600)
        elif stage == "armB_audit":
            if audit(RUNS / "armB_wsb_full"):
                s["stage"] = "armB_score_per_sb"; save_state(s)
            else:
                log("armB audit NOT FULL — blocking")
                time.sleep(1800)
        elif stage == "armB_score_per_sb":
            if score(RUNS / "armB_wsb_full", "per,songbench", "scores", None,
                     "armB_score_per_sb"):
                s["stage"] = "armB_score_mulan_amc"; save_state(s)
            else:
                time.sleep(1800)
        elif stage == "armB_score_mulan_amc":
            if score(RUNS / "armB_wsb_full", "mulan,allmusiccaps", "additional",
                     RUNS / "armB_wsb_full/scores/per_song.jsonl",
                     "armB_score_mulan_amc"):
                s["stage"] = "done"; save_state(s)
            else:
                time.sleep(1800)
        elif stage == "done":
            log("ALL STAGES COMPLETE")
            return 0


if __name__ == "__main__":
    sys.exit(main())
