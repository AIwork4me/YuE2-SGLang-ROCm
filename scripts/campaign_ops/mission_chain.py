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

Hardening (image-swap session, fixes C2/C3/C4):
  * C2: the Arm A launcher is the REPO script
    scripts/campaign_ops/run_armA_campaign.sh (the old /data/yue2 launcher copy
    only existed on the previous image).
  * C3: driver liveness via /proc scan (driver_alive.py) — never bare pgrep
    (self-match/zombie/stale false positives). The chain itself is
    single-instance via an flock held for the process lifetime.
  * C4: stage advancement is evidence-gated:
      - audit passes only on verdict parsed from audit.json (exit code AND file);
      - scoring passes only on exit 0 AND summary.json complete==true;
      - armB_acceptance REFUSES to advance without a REAL acceptance command
        (YUE2_ARMB_ACCEPTANCE_CMD env or scripts/campaign_ops/armB_acceptance.sh);
      - armB_campaign launches the Arm B driver only when Env B and its launcher
        actually exist; otherwise it records blocked_reason and keeps waiting.
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sleep = time.sleep  # module-level alias (test seam; also documents every wait)

WS = Path(os.environ.get("YUE2_WORKSPACE", "/data/yue2"))
RUNS = Path(os.environ.get("YUE2_RUNS", "/data/yue2-runs"))
# Repo location: env override first, else the repository that CONTAINS this
# script (never a hardcoded machine path — the C2 defect class; CI runners
# and fresh images clone elsewhere).
REPO = Path(os.environ.get("YUE2_REPO", str(Path(__file__).resolve().parents[2])))
STATE = WS / "mission_state.json"
LOG = WS / "logs" / "mission_chain.log"
PY_A = str(WS / "environments/yue2-torch/bin/python")
PY_B = str(WS / "environments/yue2-gfx1100/bin/python")
EV_METRICS = str(WS / "benchmark/WildSongBench/wsb_metrics/.venvs/metrics/bin/python")
WSB_ROOT = WS / "benchmark/WildSongBench"
LAUNCHER_A = REPO / "scripts/campaign_ops/run_armA_campaign.sh"
LAUNCHER_B = REPO / "scripts/campaign_ops/run_armB_campaign.sh"
ARMB_ACCEPTANCE = REPO / "scripts/campaign_ops/armB_acceptance.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO / "scripts"))
from driver_alive import driver_alive  # noqa: E402
from gpu_lock import gpu_ownership  # noqa: E402

SCORE_ENV = {
    **os.environ,
    "WSB_ROCM_TORCH_OVERRIDE": "1",
    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
    "HF_HOME": str(WS / "hf-cache"),
    "TMPDIR": str(WS / "tmp"),
    "YUE2_WORKSPACE": str(WS),
}

_chain_lock_fd: int | None = None


def log(msg: str) -> None:
    line = f"{time.strftime('%F %T')} [{msg}]"
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def acquire_chain_lock() -> bool:
    """C3: exactly ONE mission_chain per machine (flock held for lifetime)."""
    global _chain_lock_fd
    WS.mkdir(parents=True, exist_ok=True)
    fd = os.open(WS / "mission_chain.lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return False
    os.truncate(fd, 0)
    os.write(fd, json.dumps({"pid": os.getpid(),
                             "since": time.strftime("%F %T")}).encode())
    _chain_lock_fd = fd  # keep open for process lifetime
    return True


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


def launch_detached(argv: list[str], err_log: Path) -> bool:
    """Launch a detached process, capturing launch errors instead of DEVNULL."""
    try:
        err_log.parent.mkdir(parents=True, exist_ok=True)
        with err_log.open("ab") as ef:
            subprocess.Popen(argv, stdout=ef, stderr=ef, stdin=subprocess.DEVNULL,
                             start_new_session=True)
        return True
    except OSError as exc:
        log(f"launch failed {argv}: {exc}")
        return False


def audit(run_dir: Path, mode: str = "full") -> bool:
    """C4: verdict must come from the auditor's audit.json (file + exit code).

    The auditor resolves the workspace via YUE2_WORKSPACE (or repo layout);
    the chain always passes it explicitly so a bare shell environment can
    never turn into a false NOT-FULL (live defect: chain started without the
    env var made every audit fail with FileNotFoundError)."""
    env = {**os.environ, "YUE2_WORKSPACE": str(WS), "TMPDIR": str(WS / "tmp")}
    r = subprocess.run([PY_A, str(REPO / "scripts/verify_wsb_artifacts.py"),
                        "--runs", str(run_dir), "--mode", mode],
                       capture_output=True, text=True, timeout=7200, env=env)
    (run_dir / f"audit_chain_{int(time.time())}.log").write_text(
        r.stdout + "\n--- stderr ---\n" + r.stderr)
    if r.returncode != 0:
        return False
    aj = run_dir / "audit.json"
    if not aj.is_file():
        return False
    try:
        return json.loads(aj.read_text()).get("verdict") == "FULL"
    except ValueError:
        return False


def _summary_complete(out: Path) -> bool:
    sj = out / "summary.json"
    if not sj.is_file():
        return False
    try:
        return json.loads(sj.read_text()).get("complete") is True
    except ValueError:
        return False


def score(run_dir: Path, metrics: str, out_subdir: str, per_results: Path | None,
          log_name: str) -> bool:
    """Run official scoring SOLO under the GPU lock.

    RCA-F5 semantics: a COMPLETE summary is never re-run; a PARTIAL output dir
    is moved aside (scores_partial_<ts>, preserved for inspection) before a
    fresh attempt — the evaluator has no resume (handoff gotcha 7) and every
    attempt's stdout/stderr is archived separately by timestamp.

    C4: success requires exit code 0 AND a complete summary.json — a scoring
    process that exits 0 without a complete summary is a FAILURE, never a
    stage PASS.
    """
    out = run_dir / out_subdir
    if _summary_complete(out):
        log(f"{log_name}: already complete (summary.complete=true)")
        return True
    if out.exists():
        aside = run_dir / f"{out_subdir}_partial_{time.strftime('%Y%m%dT%H%M%SZ')}"
        shutil.move(str(out), str(aside))
        log(f"{log_name}: moved partial output aside -> {aside.name}")
    cmd = [EV_METRICS, "wsb_metrics/wsb_eval.py", "score",
           "--input", str(run_dir / "evaluation_inputs.jsonl"),
           "--output", str(out), "--mode", "standard", "--metrics", metrics]
    if per_results is not None:
        cmd += ["--per-results", str(per_results)]
    log(f"{log_name}: launching scoring -> {out}")
    # GPU-heavy scoring MUST hold the single-GPU ownership lock (C4; the doc
    # claim previously had no code behind it). Bounded wait; a competing
    # holder is never preempted. The lock path is derived from THIS module's
    # WS (dependency injection) — gpu_lock's process-global default must not
    # be consulted, or test/CI isolation breaks on machines without /data
    # (live defect: PR #13 CI run 44421080608, TestScoreGate PermissionError).
    # A lock that cannot be acquired within the bounded wait is a FAIL for
    # this attempt (recorded, retried later) — never a silent pass-through.
    try:
        with gpu_ownership(f"scoring:{log_name}",
                           wait_s=float(os.environ.get(
                               "YUE2_GPU_LOCK_WAIT_S", "7200")),
                           lock_path=WS / "gpu.lock"):
            proc = subprocess.run(cmd, cwd=str(WSB_ROOT), env=SCORE_ENV,
                                  capture_output=True, text=True)
    except TimeoutError as exc:
        log(f"{log_name}: GPU lock unavailable: {exc} -> FAIL (retry later)")
        return False
    ts = int(time.time())
    logs_dir = WS / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / f"{log_name}_{ts}.out").write_text(
        proc.stdout[-200000:] if proc.stdout else "")
    (logs_dir / f"{log_name}_{ts}.err").write_text(
        proc.stderr[-200000:] if proc.stderr else "")
    ok = proc.returncode == 0 and _summary_complete(out)
    log(f"{log_name}: rc={proc.returncode} summary_complete={_summary_complete(out)} "
        f"-> {'PASS' if ok else 'FAIL'}")
    return ok


def armA_driver_alive(run_dir: Path) -> tuple[bool, list[int]]:
    return driver_alive(script="run_wsb_torch.py", runs_dir=run_dir)


def armB_driver_alive(run_dir: Path) -> tuple[bool, list[int]]:
    return driver_alive(script="run_wsb.py", runs_dir=run_dir)


def run_armb_acceptance() -> tuple[bool, str]:
    """C4: REAL Arm B server acceptance only.

    Never advances on state alone. Acceptance evidence must come from an
    explicit operator-provided command (YUE2_ARMB_ACCEPTANCE_CMD) or the repo
    script scripts/campaign_ops/armB_acceptance.sh; both must exit 0.
    """
    acc_cmd = os.environ.get("YUE2_ARMB_ACCEPTANCE_CMD")
    logs_dir = WS / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    if acc_cmd:
        r = subprocess.run(["bash", "-c", acc_cmd], capture_output=True,
                           text=True, timeout=7200)
        (logs_dir / "armB_acceptance.out").write_text(r.stdout or "")
        (logs_dir / "armB_acceptance.err").write_text(r.stderr or "")
        return r.returncode == 0, f"cmd rc={r.returncode}"
    if ARMB_ACCEPTANCE.is_file():
        r = subprocess.run(["bash", str(ARMB_ACCEPTANCE)], capture_output=True,
                           text=True, timeout=7200)
        (logs_dir / "armB_acceptance.out").write_text(r.stdout or "")
        (logs_dir / "armB_acceptance.err").write_text(r.stderr or "")
        return r.returncode == 0, f"script rc={r.returncode}"
    return False, ("BLOCKED: no real Arm B acceptance command configured "
                   "(set YUE2_ARMB_ACCEPTANCE_CMD or provide "
                   "scripts/campaign_ops/armB_acceptance.sh); refusing to "
                   "advance without actual server acceptance")


def main() -> int:
    if not acquire_chain_lock():
        log("another mission_chain instance holds the chain lock; exiting")
        return 3
    while True:
        s = load_state()
        stage = s["stage"]
        log(f"stage={stage}")
        if stage == "armA_campaign":
            run_dir = RUNS / "armA_wsb_full"
            n = journal_complete(run_dir)
            alive, pids = armA_driver_alive(run_dir)
            log(f"armA journal complete={n}/384 driver_alive={alive} pids={pids}")
            if n >= 384:
                s["stage"] = "armA_audit"
                s.pop("blocked_reason", None)
                save_state(s)
            else:
                if not alive:
                    if not LAUNCHER_A.is_file():
                        s["blocked_reason"] = f"launcher missing: {LAUNCHER_A}"
                        save_state(s)
                        log(f"BLOCKED: {s['blocked_reason']}")
                    else:
                        log("armA driver not running; (re)launching resume-safe")
                        launch_detached(["setsid", "nohup", "bash", str(LAUNCHER_A)],
                                        WS / "logs" / "launcher_armA.err")
                sleep(600)
        elif stage == "armA_audit":
            if audit(RUNS / "armA_wsb_full"):
                s["stage"] = "armA_score_per_sb"
                s.pop("blocked_reason", None)
                save_state(s)
            else:
                s["blocked_reason"] = "armA audit NOT FULL — manual inspection"
                save_state(s)
                log("armA audit NOT FULL — blocking (manual inspection)")
                sleep(1800)
        elif stage == "armA_score_per_sb":
            if score(RUNS / "armA_wsb_full", "per,songbench", "scores", None,
                     "armA_score_per_sb"):
                s["stage"] = "armA_score_mulan_amc"
                s.pop("blocked_reason", None)
                save_state(s)
            else:
                s["blocked_reason"] = "armA per+songbench scoring failed"
                save_state(s)
                log("armA per+songbench scoring failed; retrying in 30min")
                sleep(1800)
        elif stage == "armA_score_mulan_amc":
            if score(RUNS / "armA_wsb_full", "mulan,allmusiccaps", "additional",
                     RUNS / "armA_wsb_full/scores/per_song.jsonl",
                     "armA_score_mulan_amc"):
                s["stage"] = "armB_acceptance"
                s.pop("blocked_reason", None)
                save_state(s)
            else:
                s["blocked_reason"] = "armA mulan+amc scoring failed"
                save_state(s)
                sleep(1800)
        elif stage == "armB_acceptance":
            ok, why = run_armb_acceptance()
            if ok:
                s["stage"] = "armB_campaign"
                s.pop("blocked_reason", None)
                save_state(s)
            else:
                s["blocked_reason"] = f"armB_acceptance: {why}"
                save_state(s)
                log(f"armB_acceptance {why}")
                sleep(1800)
        elif stage == "armB_campaign":
            run_dir = RUNS / "armB_wsb_full"
            n = journal_complete(run_dir)
            alive, pids = armB_driver_alive(run_dir)
            log(f"armB journal complete={n}/384 driver_alive={alive} pids={pids}")
            if n >= 384:
                s["stage"] = "armB_audit"
                s.pop("blocked_reason", None)
                save_state(s)
            else:
                if not alive:
                    if not Path(PY_B).is_file():
                        s["blocked_reason"] = (
                            f"Environment B not built ({PY_B} missing); "
                            "run scripts/campaign_ops/build_envB.sh first")
                        save_state(s)
                        log(f"BLOCKED: {s['blocked_reason']}")
                    elif not LAUNCHER_B.is_file():
                        s["blocked_reason"] = f"launcher missing: {LAUNCHER_B}"
                        save_state(s)
                        log(f"BLOCKED: {s['blocked_reason']}")
                    else:
                        log("armB driver not running; (re)launching resume-safe")
                        launch_detached(["setsid", "nohup", "bash", str(LAUNCHER_B)],
                                        WS / "logs" / "launcher_armB.err")
                sleep(600)
        elif stage == "armB_audit":
            if audit(RUNS / "armB_wsb_full"):
                s["stage"] = "armB_score_per_sb"
                s.pop("blocked_reason", None)
                save_state(s)
            else:
                s["blocked_reason"] = "armB audit NOT FULL — blocking"
                save_state(s)
                log("armB audit NOT FULL — blocking")
                sleep(1800)
        elif stage == "armB_score_per_sb":
            if score(RUNS / "armB_wsb_full", "per,songbench", "scores", None,
                     "armB_score_per_sb"):
                s["stage"] = "armB_score_mulan_amc"
                s.pop("blocked_reason", None)
                save_state(s)
            else:
                s["blocked_reason"] = "armB per+songbench scoring failed"
                save_state(s)
                sleep(1800)
        elif stage == "armB_score_mulan_amc":
            if score(RUNS / "armB_wsb_full", "mulan,allmusiccaps", "additional",
                     RUNS / "armB_wsb_full/scores/per_song.jsonl",
                     "armB_score_mulan_amc"):
                s["stage"] = "done"
                s.pop("blocked_reason", None)
                save_state(s)
            else:
                s["blocked_reason"] = "armB mulan+amc scoring failed"
                save_state(s)
                sleep(1800)
        elif stage == "done":
            log("ALL STAGES COMPLETE")
            return 0


if __name__ == "__main__":
    sys.exit(main())
