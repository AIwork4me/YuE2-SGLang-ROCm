#!/usr/bin/env python3
"""mutation_controls_rc5.py — RC5 mutation controls (M1 fixes + RC5 driver).

Each mutation re-introduces one dangerous behaviour (or removes one guard) in
an ISOLATED COPY of the working tree and runs the test battery that is
supposed to catch it:

    KILLED    at least one targeted test fails under the mutation  (good)
    SURVIVED  every test passes with the guard removed              (test gap)

A SURVIVED mutation is a gap in the tests: close it or accept it explicitly
with a rationale — never hide it. The copy is made with shutil (never git
stash/checkout), files are restored from an in-memory byte backup and the
restoration is verified by SHA256, so a campaign running from the live tree
is never touched.

Usage:
  python scripts/mutation_controls_rc5.py [--work /data/yue2/tmp/rc5_mutation] \
      [--out reports/w7900_rc5/01_MUTATION_RESULTS.json] [--only L1,P2,...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable

GI = "scripts/gpu_identity.py"
GL = "scripts/gpu_lifecycle.py"
LOCK = "scripts/gpu_lock.py"
RD = "scripts/server_readiness.py"
SI = "scripts/server_identity.py"
DRV = "scripts/rc5_generate.py"
T_LIFE = "tests/test_gpu_lifecycle_atomicity.py"
T_IDENT = "tests/test_gpu_identity.py"
T_READY = "tests/test_server_readiness.py"
T_SPAWN = "tests/test_server_identity_spawn.py"
T_DRV = "tests/test_rc5_generate_driver.py"
T_RWS = "tests/test_run_with_server.py"

MUTATIONS: list[dict] = [
    # ---------------------------------------------------------- lifecycle
    dict(id="L1", desc="cleanup skipped on the success path but reported CLEAN",
         file=GL, old='                    self.cleanup_state = self.cleanup()\n',
         new='                    self.cleanup_state = "CLEAN"\n',
         tests=[T_LIFE + "::test_second_job_cannot_take_the_lock_during_cleanup",
                T_RWS + "::test_1_success_stops_server"]),
    dict(id="L2", desc="identity capture not pinned to the spawned pid",
         file=GL, old='                       "--pid", str(self.spawn["pid"]))\n',
         new='                       )\n',
         tests=[T_LIFE + "::test_identity_mismatch_never_signals",
                T_LIFE + "::test_identity_receipt_never_names_a_foreign_process"]),
    dict(id="L3", desc="identity receipt used without the spawn-chain check",
         file=GL, old='if self._identity_receipt().is_file() and self._receipt_is_ours():',
         new='if self._identity_receipt().is_file():',
         tests=[T_LIFE + "::test_identity_mismatch_never_signals",
                T_LIFE + "::test_replaced_receipt_mid_session_is_refused",
                T_LIFE + "::test_stale_receipt_of_an_earlier_session_is_never_used"]),
    dict(id="L4", desc="BLOCKED marker no longer refuses the next job",
         file=LOCK, old='    blocked = read_blocked(path)\n    if blocked is not None:',
         new='    blocked = read_blocked(path)\n    if False and blocked is not None:',
         tests=[T_LIFE + "::test_stubborn_server_is_blocked_and_blocks_the_next_job"]),
    dict(id="L5", desc="BLOCKED cleared while the recorded processes are alive",
         file=LOCK, old='    live = blocked_live_processes(marker)\n    if live:',
         new='    live = blocked_live_processes(marker)\n    if False:',
         tests=[T_LIFE + "::test_stubborn_server_is_blocked_and_blocks_the_next_job"]),
    dict(id="L6", desc="gateway dies on SIGTERM (RC4.1 behaviour: lock free while the child drains)",
         file=LOCK, old='            child.send_signal(signum)\n        except ProcessLookupError:\n            pass\n        except PermissionError:',
         new='            os._exit(128 + signum)\n        except ProcessLookupError:\n            pass\n        except PermissionError:',
         tests=[T_LIFE + "::test_gateway_holds_flock_while_child_drains"]),
    dict(id="L7", desc="GPU idle floor removed (occupied device accepted)",
         file=GL, old='        ok = used_mib <= self.a.max_idle_vram_mib\n',
         new='        ok = True\n',
         tests=[T_LIFE + "::test_gpu_idle_floor_refuses_an_occupied_device"]),
    dict(id="L8", desc="GPU release no longer verified against the baseline",
         file=GL, old='        ok = mem is not None and mem[0] <= self.vram_baseline[0] \\\n            + self.a.gpu_release_tolerance_mib * 2**20\n',
         new='        ok = True\n',
         tests=[T_LIFE + "::test_gpu_release_must_return_to_baseline"]),
    dict(id="L9", desc="tree termination claimed without checking session members",
         file=GL, old='        ok = not live\n        if not ok:\n            self.blocked.extend(',
         new='        ok = True\n        if not ok:\n            self.blocked.extend(',
         tests=[T_LIFE + "::test_stubborn_scheduler_member_blocks"]),
    dict(id="L10", desc="spawn receipt accepts a reused PID (starttime not checked)",
         file=SI, old='    if f["starttime"] != str(spawn["starttime"]):\n        raise IdentError(2, f"pid {pid}: starttime',
         new='    if False:\n        raise IdentError(2, f"pid {pid}: starttime',
         tests=[T_SPAWN + "::test_verify_spawned_refuses_pid_reuse",
                T_SPAWN + "::test_cli_stop_spawned_exit_codes"]),
    dict(id="L11", desc="session membership no longer required (signals by pid only)",
         file=SI, old='    if "session" in spawn and f["session"] != int(spawn["session"]):',
         new='    if False:',
         tests=[T_SPAWN + "::test_verify_spawned_refuses_other_session"]),
    dict(id="L12", desc="tree snapshot ignores the starttime floor (PID reuse lookalikes)",
         file=SI, old='        if min_starttime is not None and int(f["starttime"]) < int(min_starttime):',
         new='        if False:',
         tests=[T_SPAWN + "::test_session_processes_only_members"]),
    # ------------------------------------------------------------- probe
    dict(id="P1", desc="probe budget unbounded again (no wall-clock deadline)",
         file=GI, old='            out_s, err_s = child.communicate(timeout=budget_s)\n        except subprocess.TimeoutExpired:\n            how = _stop_own_child(child)',
         new='            out_s, err_s = child.communicate(timeout=None)\n        except subprocess.TimeoutExpired:\n            how = _stop_own_child(child)',
         tests=[T_IDENT + "::test_probe_hard_timeout_terminates_hung_child"]),
    dict(id="P2", desc="probe timeout reported as a benign unverified identity",
         file=GI, old='        receipt["status"] = "GPU_PROGRESS_TIMEOUT"\n        receipt["reason"] = f"probe exceeded {probe_budget_s}s: {e}"\n        receipt["probe_timeout_evidence"] = getattr(e, "evidence", {})\n        ev = receipt["probe_timeout_evidence"]',
         new='        receipt["status"] = "GPU_EXECUTION_UNVERIFIED"\n        receipt["ok"] = True\n        receipt["reason"] = f"probe exceeded {probe_budget_s}s: {e}"\n        receipt["probe_timeout_evidence"] = getattr(e, "evidence", {})\n        ev = receipt["probe_timeout_evidence"]',
         tests=[T_IDENT + "::test_verify_maps_probe_timeout_to_progress_timeout"]),
    dict(id="P3", desc="real runtime probed in-process (not interruptible)",
         file=GI, old='            facts = probe_isolated(device_index, budget_s=probe_budget_s,\n                                   card=bound.get("drm_card"), sys_root=sys_root)',
         new='            facts = probe_compute(torch, device_index, full=True)',
         tests=[T_IDENT + "::test_real_torch_never_uses_in_process_probe"]),
    # ------------------------------------------------------ identity binding
    dict(id="I1", desc="two display-class PCI functions accepted (first one taken)",
         file=GI, old='    if len(cands) > 1:\n        raise IdentityUnbound(f"ambiguous display-class PCI functions for "',
         new='    if False:\n        raise IdentityUnbound(f"ambiguous display-class PCI functions for "',
         tests=[T_IDENT + "::test_two_display_class_functions_are_ambiguous"]),
    dict(id="I2", desc="PCI class filter removed (audio function can be the 'GPU')",
         file=GI, old='             if ((_read_int(p / "class") or 0) >> 16) == 0x03]',
         new='             if True]',
         tests=[T_IDENT + "::test_second_pci_function_audio_is_not_the_gpu"]),
    dict(id="I3", desc="render node not exposed to the container accepted",
         file=GI, old='    if render_node not in exposed:\n        raise IdentityUnbound(',
         new='    if False:\n        raise IdentityUnbound(',
         tests=[T_IDENT + "::test_render_node_not_exposed_to_container"]),
    dict(id="I4", desc="framework/exposed device-count bijection not required",
         file=GI, old='    if n_dev is not None and n_dev != len(exposed):',
         new='    if False:',
         tests=[T_IDENT + "::test_device_count_mismatch_is_ambiguous"]),
    dict(id="I5", desc="unique-id mismatch ignored",
         file=GI, old='    if cons is False:\n        raise IdentityUnbound(f"unique id mismatch:',
         new='    if False:\n        raise IdentityUnbound(f"unique id mismatch:',
         tests=[T_IDENT + "::test_unique_id_mismatch_fails_closed"]),
    dict(id="I6", desc="KFD device-id mismatch ignored",
         file=GI, old='                and kfd_device_id != pci_dev:',
         new='                and False:',
         tests=[T_IDENT + "::test_kfd_device_id_mismatch_fails_closed"]),
    dict(id="I7", desc="bound BDF never compared with the expected BDF",
         file=GI, old='    if expected_bdf and not bdf_matches(expected_bdf, bdf):',
         new='    if False:',
         tests=[T_IDENT + "::test_wrong_bdf_mismatch",
                T_IDENT + "::test_container_given_gpu5_of_8_binds_the_exposed_device"]),
    dict(id="I8", desc="unboundable identity reported as verified",
         file=GI, old='        receipt["status"] = "GPU_DEVICE_MISMATCH"\n        receipt["reason"] = (f"physical GPU identity could not be bound "',
         new='        receipt["status"] = "GPU_EXECUTION_UNVERIFIED"\n        receipt["ok"] = True\n        receipt["reason"] = (f"physical GPU identity could not be bound "',
         tests=[T_IDENT + "::test_framework_without_pci_ids_fails_closed",
                T_IDENT + "::test_device_count_mismatch_is_ambiguous"]),
    dict(id="I9", desc="arch mismatch downgraded to a pass",
         file=GI, old='                             f"{expected_arch!r}")\n        receipt["ok"] = False\n        return _finish(receipt, receipt_path)\n\n    # ---- physical binding',
         new='                             f"{expected_arch!r}")\n        receipt["ok"] = True\n        return _finish(receipt, receipt_path)\n\n    # ---- physical binding',
         tests=[T_IDENT + "::test_arch_mismatch_fails_loud"]),
    dict(id="I10", desc="hung probe child left running after the timeout",
         file=GI, old='        except subprocess.TimeoutExpired:\n            how = _stop_own_child(child)\n',
         new='        except subprocess.TimeoutExpired:\n            how = "already_exited"\n',
         tests=[T_IDENT + "::test_probe_hard_timeout_terminates_hung_child"]),
    # ----------------------------------------------------------- readiness
    dict(id="R0", desc="stopped (SIGSTOP) scheduler worker counted as live",
         file=RD, old='    live_workers = [w for w in workers if w["state"] not in ("Z", "T", "t")]',
         new='    live_workers = [w for w in workers if w["state"] != "Z"]',
         tests=[T_READY + "::test_stopped_scheduler_is_not_a_live_worker"]),
    dict(id="R0b", desc="explicit expected model path downgraded to a loose name match",
         file=RD, old='            ok = path_ok if want else name_ok\n',
         new='            ok = name_ok or path_ok\n',
         tests=[T_READY + "::test_explicit_model_path_is_binding_even_when_the_name_matches"]),
    dict(id="R1", desc="wrong model advertised still READY (RC4.1 behaviour)",
         file=RD, old='    if facts["models_advertised_ok"] is False:',
         new='    if False:',
         tests=[T_READY + "::test_wrong_model_advertised_is_not_ready"]),
    dict(id="R2", desc="foreign port owner still READY",
         file=RD, old='    if port_state in ("FOREIGN", "PORT_MISMATCH"):',
         new='    if False:',
         tests=[T_READY + "::test_foreign_port_owner_is_unknown",
                T_READY + "::test_url_port_mismatch_is_unknown"]),
    dict(id="R3", desc="missing progress file ignored",
         file=RD, old='    if facts.get("progress_file_missing"):',
         new='    if False:',
         tests=[T_READY + "::test_progress_file_missing_is_unknown"]),
    dict(id="R4", desc="canary trusts file size instead of decoding",
         file=RD, old='        dec = _decode_audio(wav)\n',
         new='        dec = {"decoder": "mutant", "samplerate": expect_samplerate, "channels": expect_channels, "frames": wav.stat().st_size // 8, "finite": True, "peak": 1.0, "rms": 0.1, "bytes": wav.stat().st_size}\n',
         tests=[T_READY + "::test_canary_decodes_audio_for_real"]),
    dict(id="R5", desc="stale leftover canary file no longer removed first",
         file=RD, old='    if stale.exists():\n        stale.unlink()',
         new='    if stale.exists():\n        pass',
         tests=[T_READY + "::test_canary_stale_leftover_file_is_not_success"]),
    # ------------------------------------------------------------- driver
    dict(id="D1", desc="resume regenerates verified candidates",
         file=DRV, old='                    self.complete.add(cid)\n                    already.append(cid)\n                    continue',
         new='                    already.append(cid)\n                    continue',
         tests=[T_DRV + "::test_resume_never_regenerates_verified_candidates"]),
    dict(id="D2", desc="official budget lowered (ode_steps 32 -> 16)",
         file=DRV, old='"ode_steps": 32, "semantic_max_tokens": 9000, "abc_max_tokens": 4096,',
         new='"ode_steps": 16, "semantic_max_tokens": 9000, "abc_max_tokens": 4096,',
         tests=[T_DRV + "::test_generate_publish_journal_checkpoint_and_official_acceptance"]),
    dict(id="D3", desc="damaged bundle not detected on resume",
         file=DRV, old='                    self.verify_result(cand)\n                    req = read_json(cand / "request.json")',
         new='                    req = read_json(cand / "request.json")',
         tests=[T_DRV + "::test_damaged_bundle_is_quarantined_and_regenerated"]),
    dict(id="D4", desc="identity drift on resume accepted",
         file=DRV, old='            if drift:\n                print("FATAL: run_config.json identity drift',
         new='            if False:\n                print("FATAL: run_config.json identity drift',
         tests=[T_DRV + "::test_identity_drift_is_refused"]),
    dict(id="D5", desc="quarantine deletes evidence instead of moving it",
         file=DRV, old='        shutil.move(str(path), str(dest))\n        fsync_dir(q.parent)',
         new='        shutil.rmtree(str(path), ignore_errors=True)\n        fsync_dir(q.parent)',
         tests=[T_DRV + "::test_damaged_bundle_is_quarantined_and_regenerated"]),
    dict(id="D6", desc="seed taken from a counter instead of the official manifest",
         file=DRV, old='        payload = {"style": row["style"], "lyrics": row["lyrics"], "seed": e["seed"],',
         new='        payload = {"style": row["style"], "lyrics": row["lyrics"], "seed": 831001 + e["prompt_index"],',
         tests=[T_DRV + "::test_generate_publish_journal_checkpoint_and_official_acceptance"]),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make_copy(src: Path, work: Path) -> None:
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(src, work, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "*.pyc", ".pytest_cache"))


def run_tests(work: Path, tests: list[str], timeout: float) -> subprocess.CompletedProcess:
    env = dict(os.environ, YUE2_WORKSPACE=os.environ.get("YUE2_WORKSPACE", "/data/yue2"))
    env.pop("YUE2_ALLOW_CPU", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        return subprocess.run([PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
                               *tests], cwd=work, capture_output=True, text=True, timeout=timeout,
                              env=env)
    except subprocess.TimeoutExpired as e:
        class R:  # a timeout is NOT a kill: the tests did not detect the mutation
            returncode = "TIMEOUT"
            stdout = (e.stdout or b"") if isinstance(e.stdout, bytes) else str(e.stdout or "")
        out = getattr(e, "stdout", None)
        if isinstance(out, bytes):
            out = out.decode(errors="replace")
        r = subprocess.CompletedProcess([], "TIMEOUT", (out or ""), getattr(e, "stderr", "") or "")
        return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=REPO)
    ap.add_argument("--work", type=Path, default=Path("/data/yue2/tmp/rc5_mutation"))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--timeout", type=float, default=2400.0)
    a = ap.parse_args()
    make_copy(a.src, a.work)
    only = set(a.only.split(",")) if a.only else None
    results = []
    for m in MUTATIONS:
        if only and m["id"] not in only:
            continue
        p = a.work / m["file"]
        original = p.read_bytes()
        text = original.decode()
        print(f"[{m['id']}] {m['desc']}", flush=True)
        if m["old"] not in text:
            results.append({**{k: m[k] for k in ("id", "desc", "file")},
                            "result": "NOT_RUN", "reason": "mutation pattern not found"})
            print("    -> NOT_RUN (pattern not found)")
            continue
        try:
            p.write_text(text.replace(m["old"], m["new"], 1))
            t0 = time.time()
            r = run_tests(a.work, m["tests"], a.timeout)
            tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
            skipped = "skipped" in (r.stdout or "")
            if r.returncode == "TIMEOUT":
                res = "SURVIVED"
                why = "tests timed out under the mutation (no detection)"
            else:
                res = "KILLED" if r.returncode != 0 else "SURVIVED"
                why = tail[0][:160]
            results.append({**{k: m[k] for k in ("id", "desc", "file")},
                            "tests": m["tests"], "result": res, "pytest_rc": r.returncode,
                            "pytest_tail": why, "seconds": round(time.time() - t0, 1)})
            print(f"    -> {res} (rc={r.returncode}, {round(time.time() - t0, 1)}s) {why[:100]}",
                  flush=True)
        finally:
            p.write_bytes(original)
            if sha(p) != hashlib.sha256(original).hexdigest():
                raise SystemExit(f"RESTORE FAILED for {m['file']}")
    out = {"receipt_type": "rc5_mutation_controls",
           "executed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "isolated_copy": str(a.work),
           "source_head_dirty": bool(subprocess.run(
               ["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True).stdout),
           "results": results}
    out["summary"] = {r["id"]: r["result"] for r in results}
    out["killed"] = sum(1 for r in results if r["result"] == "KILLED")
    out["survived"] = [r["id"] for r in results if r["result"] == "SURVIVED"]
    out["not_run"] = [r["id"] for r in results if r["result"] == "NOT_RUN"]
    dest = a.out or REPO / "reports/w7900_rc5/01_MUTATION_RESULTS.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    prev = {}
    if dest.is_file() and only:      # merge partial runs
        try:
            prev = {r["id"]: r for r in json.loads(dest.read_text()).get("results", [])}
        except ValueError:
            prev = {}
    for r in results:
        prev[r["id"]] = r
    out["results"] = [prev[k] for k in sorted(prev)]
    out["summary"] = {r["id"]: r["result"] for r in out["results"]}
    out["survived"] = [r["id"] for r in out["results"] if r["result"] == "SURVIVED"]
    out["not_run"] = [r["id"] for r in out["results"] if r["result"] == "NOT_RUN"]
    out["killed"] = sum(1 for r in out["results"] if r["result"] == "KILLED")
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"], indent=0))
    print(f"killed={out['killed']} survived={out['survived'] or 'none'} "
          f"not_run={out['not_run'] or 'none'}; raw: {dest}")
    return 0 if not out["survived"] and not out["not_run"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
