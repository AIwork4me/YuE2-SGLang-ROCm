#!/usr/bin/env python3
"""Completion supervisor for the gfx1151 WildSongBench run.

DESIGN CONTRACT (mission: safe benchmark completion handoff)
- Read-only toward the live experiment: never interrupts a candidate, never
  mutates generation parameters, never restarts a failed generation.
- Idempotent: a flock prevents concurrent instances; every poll cycle can be
  interrupted and resumed; scoring is retried only from incomplete states.
- Durable log + persistent state machine (supervisor/state.json).
- All paths absolute and env-configurable.
- Gates A-G must ALL pass before official scoring begins; any failure => no
  scoring, evidence preserved, blocker recorded. Never reports FULL falsely.
- Git: evidence repo 'main' only; the W7900 validation branch
  (validation/gfx1100-rocm7141, internal PR #1) is never touched; pushes are
  verified against the remote SHA before being logged as pushed.
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

WS = Path(os.environ.get("WS", "/home/amd/Desktop/YuE2"))
RUNS = Path(os.environ.get("RUNS", str(WS / "runs/wsb_full")))
EV = Path(os.environ.get("EV", str(WS / "evidence/YuE2-SGLang-ROCm")))
VENV = Path(os.environ.get("VENV", str(WS / "environments/yue2")))
SUP = WS / "supervisor"
LOG = WS / "logs/supervisor.log"
STATE = SUP / "state.json"
WSB = WS / "benchmark/WildSongBench"
AUDITOR = WS / "scripts/verify_wsb_artifacts.py"
POLL_SECONDS = int(os.environ.get("SUPERVISOR_POLL", "600"))
GIT_AUTHOR = "-c user.name=AIwork4me -c user.email=AIwork4me@users.noreply.github.com"


def log(msg: str) -> None:
    line = f"{time.strftime('%F %T')} {msg}"
    with LOG.open("a") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if STATE.is_file():
        return json.loads(STATE.read_text())
    return {"phase": "WAITING_FOR_GENERATION", "cycles": 0, "history": []}


def save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(STATE)


def record(state: dict, event: str) -> None:
    state["history"] = (state.get("history") or [])[-200:] + [
        {"t": time.strftime("%F %T"), "event": event}]
    save_state(state)


def proc_alive(pattern: str) -> bool:
    return subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0


def result_json_count() -> int:
    return len(list(RUNS.glob("songs/*/result.json")))


def git_push_verified(cwd: Path) -> tuple[bool, str]:
    """Push and verify the REMOTE actually carries our HEAD before claiming success."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True).stdout.strip()
    for attempt in range(6):
        subprocess.run(["git", "push"], cwd=cwd, capture_output=True, timeout=120)
        remote = subprocess.run(["git", "ls-remote", "origin", "refs/heads/main"],
                                cwd=cwd, capture_output=True, text=True, timeout=60).stdout.split()[0:1]
        if remote and remote[0] == head:
            return True, head
        time.sleep(20)
    return False, head


def gtt_free_bytes() -> int:
    total = used = 0
    for base in Path("/sys/class/drm").glob("card*/device"):
        try:
            t = int((base / "mem_info_gtt_total").read_text())
            u = int((base / "mem_info_gtt_used").read_text())
            total, used = max(total, t), max(used, u)
        except (OSError, ValueError):
            continue
    return total - used


def mem_available_kib() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable"):
            return int(line.split()[1])
    return 0


def run_full_audit() -> tuple[int, dict]:
    """Run the strict full-mode auditor; returns (exit_code, parsed audit.json)."""
    proc = subprocess.run([str(VENV / "bin/python"), str(AUDITOR), "--runs", str(RUNS),
                           "--mode", "full"], capture_output=True, text=True, cwd=str(WS))
    audit_path = RUNS / "audit.json"
    audit = json.loads(audit_path.read_text()) if audit_path.is_file() else {}
    return proc.returncode, audit


def evaluator_ready() -> tuple[bool, str]:
    checks = []
    for venv in ("metrics", "eval"):
        py = WSB / "wsb_metrics" / ".venvs" / venv / "bin" / "python"
        checks.append((f"venv:{venv}", py.is_file()))
    checks.append(("inputs", (RUNS / "evaluation_inputs.jsonl").is_file()))
    code = ("import sys; sys.path.insert(0, '" + str(WSB / "wsb_metrics") + "'); "
            "from wsb_eval import verify_release; verify_release(); print('RELEASE_OK')")
    proc = subprocess.run([str(VENV / "bin/python"), "-c", code], capture_output=True, text=True)
    checks.append(("frozen-release-hashes", proc.returncode == 0 and "RELEASE_OK" in proc.stdout))
    models = WSB / "wsb_metrics/evaluation_models"
    checks.append(("evaluator-models", models.is_dir() and any(models.iterdir())))
    failed = [name for name, ok in checks if not ok]
    return (not failed), ",".join(failed)


def gate_report(audit_code: int, audit: dict) -> dict:
    driver_gone = not proc_alive("run_wsb.py --runs runs/wsb_full")
    watcher_gone = not proc_alive("milestone_watcher")
    return {
        "A generation ended (driver+watcher gone)": driver_gone and watcher_gone,
        "B auditor exit code zero": audit_code == 0,
        "C 384/384 verified": audit.get("verified_complete") == 384
                              and audit.get("expected_candidates") == 384,
        "D 192 prompts x 2 candidates": audit.get("expected_prompt_indices") == 192,
        "E no unresolved problems": audit_code == 0 and not audit.get("problems"),
        "F evaluator ready (final verdict recorded separately)": None,  # filled by caller
        "G GPU headroom (>=20 GiB GTT free, >=16 GiB RAM avail)": None,  # filled by caller
    }


def snapshot_dir_if_incomplete(path: Path) -> None:
    """Retry safety: never silently overwrite a previous scoring attempt."""
    if not path.exists() or not any(path.iterdir()):
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.attempt_{stamp}.bak")
    shutil.move(str(path), str(backup))
    log(f"preserved previous scoring attempt: {backup.name}")


def run_scoring() -> dict:
    """Official scoring: per,songbench then mulan,allmusiccaps (no Q3O)."""
    import urllib.request
    env = dict(os.environ, WSB_ROCM_TORCH_OVERRIDE="1")
    cmds = [
        (["--mode", "standard", "--metrics", "per,songbench"],
         RUNS / "scores"),
        (["--per-results", str(RUNS / "scores/per_song.jsonl"),
          "--mode", "standard", "--metrics", "mulan,allmusiccaps"],
         RUNS / "additional"),
    ]
    for extra, out_dir in cmds:
        if out_dir.name == "additional":
            # second stage requires the first stage's per_song.jsonl
            if not (RUNS / "scores/per_song.jsonl").is_file():
                return {"ok": False, "failed_at": "missing per_song.jsonl"}
        summary = out_dir / "summary.json"
        if summary.is_file():
            try:
                if json.loads(summary.read_text()).get("complete"):
                    log(f"scoring already complete: {out_dir.name} (idempotent skip)")
                    continue
            except Exception:
                pass
        snapshot_dir_if_incomplete(out_dir)
        cmd = [str(VENV / "bin/python"), str(WSB / "wsb_metrics/wsb_eval.py"), "score",
               "--input", str(RUNS / "evaluation_inputs.jsonl"),
               "--output", str(out_dir)] + extra
        log(f"scoring: {' '.join(extra)}")
        proc = subprocess.run(cmd, cwd=str(WSB), env=env,
                              stdout=(WS / "logs/scoring_per.log").open("a")
                              if out_dir.name == "scores" else (WS / "logs/scoring_additional.log").open("a"),
                              stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            return {"ok": False, "failed_at": str(out_dir), "rc": proc.returncode}
        summary = out_dir / "summary.json"
        complete = summary.is_file() and json.loads(summary.read_text()).get("complete")
        if not complete:
            return {"ok": False, "failed_at": f"{out_dir.name} incomplete"}
    return {"ok": True}


def cross_validate() -> dict:
    """Independent recomputation and cross-check of the official scoring.

    Checks (all must pass; every check records its evidence):
      1. coverage: 384 PER rows, 384 songbench receipts, standard mode, complete
      2. selection: recompute the official min-key selection (per, edits,
         |asr-phonemes - reference-phonemes|, candidate_index) from raw
         receipts and compare to the evaluator's recorded selected_candidates
      3. PER aggregates: sum(edits)/sum(reference_phonemes) over the 384 and
         over the 192 selected, vs the evaluator's summary values
      4. SongBench means: recompute the 7 dimension means + Global Avg over
         the 192 selected from receipts/<id>/songbench.json vs summary
      5. additional metrics (mulan, allmusiccaps): coverage + selected-set
         identity vs the PER selection; means recomputed when the receipt
         exposes a simple scalar field
    """
    import math
    checks, problems = [], []

    def check(name, ok, detail=""):
        checks.append({"check": name, "passed": bool(ok), "detail": str(detail)[:300]})
        if not ok:
            problems.append(f"{name}: {str(detail)[:200]}")

    per_rows = [json.loads(l) for l in (RUNS / "scores/per_song.jsonl").read_text().splitlines() if l.strip()]
    summary = json.loads((RUNS / "scores/summary.json").read_text())
    check("per coverage 384", len(per_rows) == 384, len(per_rows))
    check("scores summary complete", summary.get("complete") is True, summary.get("errors"))
    check("standard mode + full coverage flag",
          summary.get("mode") == "standard" and summary.get("full_192_standard_candidate_coverage") is True,
          (summary.get("mode"), summary.get("full_192_standard_candidate_coverage")))

    # selection recompute with the official key
    def official_key(r):
        m = r["metrics"]["per"]
        repeat = m["asr_repeats"][m["selected_asr_repeat"]]
        return (m["per"], m["edits"],
                abs(len(repeat["phonemes"]) - m["reference_phonemes"]),
                r["candidate_index"])

    by_prompt = {}
    for r in per_rows:
        by_prompt.setdefault(r["prompt_index"], []).append(r)
    selected_ids = []
    for i in range(192):
        rows = by_prompt.get(i, [])
        if len(rows) == 2:
            selected_ids.append(min(rows, key=official_key)["id"])
        else:
            problems.append(f"selection: prompt {i} has {len(rows)} candidates")
    evaluator_pick = [f"wsb_{r['prompt_index']:03d}_r{r['candidate_index']}_s{r['seed']}"
                      for r in summary.get("selected_candidates", [])]
    check("selection identical to evaluator (192)", selected_ids == evaluator_pick,
          f"recomputed {len(selected_ids)}, evaluator {len(evaluator_pick)}, "
          f"mismatches {sum(a != b for a, b in zip(selected_ids, evaluator_pick))}")

    # PER aggregates
    def per_micro(rows):
        return sum(r["metrics"]["per"]["edits"] for r in rows) / \
               sum(r["metrics"]["per"]["reference_phonemes"] for r in rows)
    sel_rows = [r for r in per_rows if r["id"] in set(selected_ids)]
    groups = summary.get("unselected_candidates", {}).get("groups", {}).get("all", {}).get("per", {})
    ev_micro_all = groups.get("per_micro")
    check("PER micro (384) recomputed == evaluator",
          ev_micro_all is not None and math.isclose(per_micro(per_rows), ev_micro_all, rel_tol=1e-9),
          f"recomputed {per_micro(per_rows):.10f} vs {ev_micro_all}")
    sel_groups = summary.get("standard_selected", {}).get("groups", {}).get("all", {}).get("per", {})
    ev_micro_sel = sel_groups.get("per_micro")
    check("PER micro (192 selected) recomputed == evaluator",
          ev_micro_sel is not None and math.isclose(per_micro(sel_rows), ev_micro_sel, rel_tol=1e-9),
          f"recomputed {per_micro(sel_rows):.10f} vs {ev_micro_sel}")

    # SongBench means over selected 192 from raw receipts
    dims = None
    acc = {}
    n_sb = 0
    for ident in selected_ids:
        receipt = RUNS / "scores" / "receipts" / ident / "songbench.json"
        if not receipt.is_file():
            problems.append(f"songbench receipt missing: {ident}")
            continue
        sb = json.loads(receipt.read_text())
        sb = sb.get("result", sb)
        raw = sb.get("songbench") or sb.get("songbench_raw") or {}
        if not raw:
            continue
        n_sb += 1
        for k, v in raw.items():
            if isinstance(v, (int, float)):
                acc[k] = acc.get(k, 0.0) + v
        dims = dims or sorted(k for k, v in raw.items() if isinstance(v, (int, float)))
    check("songbench receipts for all 192 selected", n_sb == 192, n_sb)
    ev_sb = summary.get("standard_selected", {}).get("groups", {}).get("all", {}).get("songbench", {}).get("means", {})
    recomputed_means = {k: acc[k] / n_sb for k in dims} if dims and n_sb else {}
    for k, ev in ev_sb.items():
        if k in recomputed_means:
            # receipts store 4-decimal rounded scores; the summary is full
            # precision -> compare at rounding tolerance, not bit tolerance
            check(f"songbench mean {k}",
                  math.isclose(recomputed_means[k], ev, rel_tol=1e-9, abs_tol=1e-4),
                  f"recomputed {recomputed_means[k]:.6f} vs {ev} (delta {abs(recomputed_means[k]-ev):.2e})")
    if "Global Avg" in ev_sb and dims:
        ga = sum(recomputed_means.values()) / len(recomputed_means)
        check("songbench mean Global Avg",
              math.isclose(ga, ev_sb["Global Avg"], rel_tol=1e-9, abs_tol=2e-4),
              f"recomputed {ga:.6f} vs {ev_sb['Global Avg']} (delta {abs(ga-ev_sb['Global Avg']):.2e})")

    # additional metrics: coverage + selected-set identity (+ means when scalar detectable)
    add_summary_path = RUNS / "additional/summary.json"
    if add_summary_path.is_file():
        add = json.loads(add_summary_path.read_text())
        check("additional summary complete", add.get("complete") is True, add.get("errors"))
        add_sel = [f"wsb_{r['prompt_index']:03d}_r{r['candidate_index']}_s{r['seed']}"
                   for r in add.get("selected_candidates", [])]
        check("additional selected-set identical to PER selection", add_sel == selected_ids,
              f"{len(add_sel)} vs {len(selected_ids)}")
        for metric in ("mulan", "allmusiccaps"):
            receipts = sorted((RUNS / "additional/receipts").glob(f"*/{metric}.json")) \
                if (RUNS / "additional/receipts").is_dir() else []
            check(f"{metric} receipts coverage", len(receipts) == 192, len(receipts))
            vals = []
            for rp in receipts:
                d = json.loads(rp.read_text())
                d = d.get("result", d)
                m = d.get("metrics", {}).get(metric, d.get(metric, {}))
                if isinstance(m, dict):
                    scal = [v for v in m.values() if isinstance(v, (int, float))]
                    if len(scal) == 1:
                        vals.append(scal[0])
                    elif "mean" in m:
                        vals.append(m["mean"])
                elif isinstance(m, (int, float)):
                    vals.append(m)
            if vals and len(vals) == 192:
                ev = add.get("standard_selected", {}).get("groups", {}).get("all", {}).get(metric, {})
                ev_mean = ev.get("mean") if isinstance(ev, dict) else ev
                if isinstance(ev_mean, (int, float)):
                    check(f"{metric} mean recomputed == evaluator",
                          math.isclose(sum(vals) / len(vals), ev_mean, rel_tol=1e-6, abs_tol=1e-9),
                          f"recomputed {sum(vals)/len(vals):.8f} vs {ev_mean}")
            else:
                checks.append({"check": f"{metric} mean recomputed",
                               "passed": None,
                               "detail": f"scalar not auto-detectable from receipts ({len(vals)} values); "
                                         "means compared only via evaluator summary; counts verified"})
    else:
        problems.append("additional/summary.json missing")

    return {"at": time.strftime("%F %T"),
            "checks": checks,
            "problems": problems,
            "passed": not problems}


def build_selection_audit() -> dict:
    """Mechanical extraction of the official PER selection for all 192 prompts."""
    per = [json.loads(l) for l in (RUNS / "scores/per_song.jsonl").read_text().splitlines() if l.strip()]
    by_prompt: dict[int, list] = {}
    for r in per:
        by_prompt.setdefault(r["prompt_index"], []).append(r)
    audit_rows, problems = [], []
    for i in range(192):
        rows = sorted(by_prompt.get(i, []), key=lambda r: r["candidate_index"])
        if len(rows) != 2:
            problems.append(f"prompt {i}: {len(rows)} candidates scored")
            continue
        def key(r):
            m = r.get("metrics", {}).get("per", {})
            return (m.get("per"), m.get("edits"), abs(m.get("hypothesis_phonemes", 0) - m.get("reference_phonemes", 0)), r["candidate_index"])
        selected = min(rows, key=key)
        official_pick = None
        audit_rows.append({
            "prompt_index": i,
            "selected_candidate_index": selected["candidate_index"],
            "selected_id": selected["id"],
            "per": selected.get("metrics", {}).get("per", {}).get("per"),
            "both_candidates": [{"candidate_index": r["candidate_index"],
                                 "per": r.get("metrics", {}).get("per", {}).get("per"),
                                 "edits": r.get("metrics", {}).get("per", {}).get("edits")} for r in rows],
        })
    return {"prompts": len(audit_rows), "problems": problems, "rows": audit_rows}


def package_evidence() -> list[Path]:
    """Copy small, decision-relevant artifacts into the evidence repo (never audio)."""
    targets = []
    safe_copies = {
        RUNS / "audit.json": "evidence/final_generation_audit.json",
        RUNS / "generation_summary.json": "evidence/generation_summary.json",
        RUNS / "generation_manifest.jsonl": "evidence/generation_manifest.jsonl",
        RUNS / "scores/summary.json": "evidence/official_scores.json",
        RUNS / "scores/per_song.jsonl": "evidence/per_song.jsonl",
        RUNS / "scores/per.environment.json": "evidence/evaluator_environment_per.json",
        RUNS / "additional/summary.json": "evidence/official_scores_additional.json",
    }
    for src, rel in safe_copies.items():
        if src.is_file():
            dst = EV / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            targets.append(dst)
    # per-prompt CSV from the selection audit
    sel = build_selection_audit()
    (EV / "evidence/selection_audit.json").write_text(json.dumps(sel, indent=2) + "\n")
    csv = ["prompt_index,selected_candidate_index,selected_per"]
    csv += [f"{r['prompt_index']},{r['selected_candidate_index']},{r['per']}" for r in sel["rows"]]
    (EV / "evidence/per_prompt_scores.csv").write_text("\n".join(csv) + "\n")
    return targets


def main() -> int:
    SUP.mkdir(parents=True, exist_ok=True)
    lock_file = SUP / "supervisor.lock"
    lf = lock_file.open("w")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another supervisor instance holds the lock; exiting")
        return 0

    state = load_state()
    state["cycles"] = state.get("cycles", 0) + 1
    record(state, f"cycle start (phase={state['phase']})")

    while True:
        done = result_json_count()
        driver = proc_alive("run_wsb.py --runs runs/wsb_full")
        log(f"poll: result.json={done} driver_alive={driver}")

        if driver and done < 384:
            time.sleep(POLL_SECONDS)
            continue

        # Generation process has ended (or 384 reached and driver finishing last candidate)
        if not driver and done < 384:
            # Unexpected termination: record, do NOT restart, do NOT score.
            record(state, f"BLOCKED: generation process ended with {done}/384 candidates "
                          f"(in-flight candidate may be incomplete); no restart attempted")
            state["phase"] = "BLOCKED_GENERATION_INCOMPLETE"
            state["blocked_at_count"] = done
            state["blocked_since"] = time.strftime("%F %T")
            save_state(state)
            log(f"BLOCKED at {done}/384 — preserving evidence; supervisor will keep polling "
                "in case an operator resumes the run (resume_wsb.py), but never scores short of 384")
            time.sleep(POLL_SECONDS)
            continue

        # done >= 384 and driver gone: wait for the milestone watcher to finish its final commit
        if proc_alive("milestone_watcher"):
            log("384 reached; waiting for milestone watcher to exit before touching the git worktree")
            time.sleep(60)
            continue

        record(state, "generation complete; running strict full audit")
        audit_code, audit = run_full_audit()
        ready, failed_checks = evaluator_ready()
        gates = gate_report(audit_code, audit)
        gates["F evaluator ready (final verdict recorded separately)"] = ready
        gates["G GPU headroom (>=20 GiB GTT free, >=16 GiB RAM avail)"] = (
            gtt_free_bytes() >= 20 * 2**30 and mem_available_kib() >= 16 * 2**20)
        gate_dump = {"audit": {k: audit.get(k) for k in
                               ("expected_candidates", "verified_complete", "problems", "verdict")},
                     "gates": gates, "evaluator_failed_checks": failed_checks,
                     "gtt_free_bytes": gtt_free_bytes(), "mem_available_kib": mem_available_kib(),
                     "at": time.strftime("%F %T")}
        (SUP / "gate_report.json").write_text(json.dumps(gate_dump, indent=2) + "\n")
        log(f"gates: {json.dumps({k: v for k, v in gates.items()})}")

        if not all(v is True for v in gates.values()):
            state["phase"] = "BLOCKED_GATES_FAILED"
            save_state(state)
            log("BLOCKED: gates failed — no scoring, evidence preserved (see supervisor/gate_report.json)")
            return 1

        record(state, "all gates passed; beginning official scoring")
        state["phase"] = "SCORING"
        save_state(state)
        result = run_scoring()
        if not result.get("ok"):
            state["phase"] = "SCORING_FAILED"
            state["scoring_failure"] = result
            save_state(state)
            log(f"SCORING FAILED: {json.dumps(result)} — attempts preserved; retry-safe")
            return 1

        record(state, "scoring complete; running cross-validation")
        state["phase"] = "CROSS_VALIDATION"
        save_state(state)
        cv = cross_validate()
        (SUP / "cross_validation.json").write_text(json.dumps(cv, indent=2) + "\n")
        shutil.copyfile(SUP / "cross_validation.json",
                        EV / "evidence/cross_validation.json")
        if not cv["passed"]:
            state["phase"] = "BLOCKED_CROSSVAL_MISMATCH"
            state["crossval_problems"] = cv["problems"][:20]
            save_state(state)
            log(f"BLOCKED: cross-validation mismatches: {cv['problems'][:5]}")
            return 1
        record(state, f"cross-validation passed ({len(cv['checks'])} checks)")

        record(state, "packaging evidence")
        package_evidence()
        # Commit to evidence repo main only (never the validation branch).
        subprocess.run(["git", "checkout", "main"], cwd=EV, capture_output=True)
        subprocess.run("git add -A", shell=True, cwd=EV, capture_output=True)
        subprocess.run(f'git {GIT_AUTHOR} commit -q -m "bench(wsb): complete 384-candidate generation and official scoring on gfx1151\n\n'
                       f'- strict full-mode audit verdict FULL (gates in supervisor/gate_report.json)\n'
                       f'- official per,songbench + mulan,allmusiccaps scored (ROCm evaluator patches 0006/0007,\n'
                       f'  ASR backend: qwen_asr/transformers; equivalence with CUDA/vLLM NOT claimed)\n'
                       f'- selection audit for 192 prompts; per-prompt CSV; environment receipts"',
                       shell=True, cwd=EV, capture_output=True)
        ok, head = git_push_verified(EV)
        record(state, f"evidence commit {'pushed' if ok else 'PUSH-FAILED'} at {head}")
        state["phase"] = "SCORING_COMPLETE"
        state["evidence_head"] = head
        state["push_verified"] = ok
        save_state(state)
        log(f"SCORING COMPLETE; evidence at {head}; push_verified={ok}; "
            "remaining: final reviews + report (operator/model session)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
