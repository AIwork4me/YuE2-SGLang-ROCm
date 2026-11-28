#!/usr/bin/env python3
"""rc61_baseline.py — M0 live audit generator for RC6.1.

Collects the live git/GitHub/CI/resource state into
reports/developer_reference/rc6_1/00_BASELINE.json and
00_RESOURCE_PREFLIGHT.json. Read-only with respect to evidence; writes only
into the rc6_1 report directory. GitHub fields degrade honestly (marked
OFFLINE) when gh/network is unavailable — they are never fabricated.

Usage:
  python3 scripts/rc61_baseline.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "reports/developer_reference/rc6_1"
RC6_DIR = REPO / "reports/developer_reference"

KNOWN = {
    "pr_number": 20,
    "pr_head_sha": "eeb2115fb5411c12ff7de415c1cb8a61702b7700",
    "base_sha": "57e81c2ccb664a4a5eedf9a9526d0709647ba9aa",
    "push_workflow": 46039316593,
    "pull_request_workflow": 46039324475,
}


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                       cwd=str(cwd) if cwd else None)
    return p.returncode, (p.stdout or "").strip()


def gpu_physical_identity() -> dict:
    """Closed physical chain: exposed render node -> sysfs PCI BDF + unique_id.

    No 'first AMD GPU' guessing: the container exposes exactly one amdgpu
    render node; ambiguity is reported, not silently resolved.
    """
    dri = Path("/dev/dri")
    render_nodes = sorted(p.name for p in dri.glob("renderD*")) if dri.is_dir() else []
    cards = sorted(p.name for p in dri.glob("card*")) if dri.is_dir() else []
    # A card node present in /dev/dri is what the container was actually given;
    # map each visible card (and its render node) to the sysfs PCI function.
    sysfs = Path("/sys/class/drm")
    visible_bdfs, unique_ids = {}, {}
    for node in sorted(sysfs.iterdir(), key=lambda p: p.name):
        if not node.name.startswith("card") or node.name.startswith("card-"):
            continue
        idx = node.name[4:]
        if idx.isdigit() and (dri / node.name).exists():
            ue = (node / "device" / "uevent").read_text() if (node / "device" / "uevent").is_file() else ""
            m = re.search(r"PCI_SLOT_NAME=(\S+)", ue)
            if m:
                visible_bdfs[node.name] = m.group(1)
                uid = (node / "device" / "unique_id").read_text().strip() \
                    if (node / "device" / "unique_id").is_file() else None
                if uid:
                    unique_ids[m.group(1)] = uid
    amdgpu_bdfs = []
    for node in sorted(sysfs.iterdir(), key=lambda p: p.name):
        if not node.name.startswith("card") or node.name.startswith("card-"):
            continue
        ue = (node / "device" / "uevent").read_text() if (node / "device" / "uevent").is_file() else ""
        drv = (node / "device" / "driver").resolve().name if (node / "device" / "driver").is_symlink() else ""
        m = re.search(r"PCI_SLOT_NAME=(\S+)", ue)
        if m and drv == "amdgpu":
            amdgpu_bdfs.append(m.group(1))
    bdf = list(visible_bdfs.values())[0] if len(visible_bdfs) == 1 else None
    return {
        "kfd_present": Path("/dev/kfd").exists(),
        "render_nodes_visible": render_nodes,
        "card_nodes_visible": cards,
        "host_amdgpu_bdfs": sorted(amdgpu_bdfs),
        "exposed_bdf": bdf,
        "exposed_unique_id": unique_ids.get(bdf) if bdf else None,
        "multi_gpu_host_note": (
            f"host has {len(amdgpu_bdfs)} amdgpu functions; this container exposes "
            f"{len(visible_bdfs)} render-capable card node(s) — the lock domain covers "
            "THIS visible device only; sibling GPUs are not addressable from here"),
        "unambiguous": len(render_nodes) == 1 and len(visible_bdfs) == 1,
    }


def cgroup_limits() -> dict:
    out = {}
    for name, f in (("memory_max_bytes", "/sys/fs/cgroup/memory.max"),
                    ("memory_current_bytes", "/sys/fs/cgroup/memory.current"),
                    ("memory_high_bytes", "/sys/fs/cgroup/memory.high"),
                    ("cpu_max", "/sys/fs/cgroup/cpu.max"),
                    ("pids_max", "/sys/fs/cgroup/pids.max")):
        try:
            out[name] = Path(f).read_text().strip()
        except OSError:
            out[name] = None
    mx = out.get("memory_max_bytes")
    out["memory_limit_gib"] = round(int(mx) / 2**30, 3) if mx and mx.isdigit() else None
    cur = out.get("memory_current_bytes")
    out["memory_current_gib"] = round(int(cur) / 2**30, 3) if cur and cur.isdigit() else None
    cm = out.get("cpu_max")
    if cm and " " in cm:
        quota, period = cm.split()
        out["cpu_effective_cores"] = round(int(quota) / int(period), 2) if quota != "max" else None
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # ---- git ----
    local_head, subject = run(["git", "rev-parse", "HEAD"]), None
    head = local_head[1]
    rc, dirty = run(["git", "status", "--porcelain"])
    rc, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    rc, subject = run(["git", "log", "-1", "--format=%s"])

    # ---- github (live; honest degradation) ----
    gh_state = {"available": False, "note": "gh/network unavailable — OFFLINE"}
    try:
        rc, body = run(["gh", "pr", "view", str(KNOWN["pr_number"]),
                        "--json", "state,isDraft,headRefOid,mergeable,url"])
        if rc == 0 and body:
            pr = json.loads(body)
            rc2, runs = run(["gh", "api",
                             f"repos/AIwork4me/YuE2-SGLang-ROCm/actions/runs"
                             f"?head_sha={KNOWN['pr_head_sha']}&per_page=20"])
            ci = []
            if rc2 == 0 and runs:
                for r in json.loads(runs).get("workflow_runs", []):
                    ci.append({"id": r["id"], "name": r["name"], "event": r["event"],
                               "status": r["status"], "conclusion": r["conclusion"]})
            gh_state = {
                "available": True,
                "pr": {"state": pr["state"], "is_draft": pr["isDraft"],
                       "head_sha": pr["headRefOid"], "mergeable": pr["mergeable"],
                       "url": pr.get("url")},
                "exact_head_ci": ci,
                "head_matches_known": pr["headRefOid"] == KNOWN["pr_head_sha"],
                "ci_all_success": bool(ci) and all(c["conclusion"] == "success" for c in ci),
                "push_workflow_id_present": any(c["id"] == KNOWN["push_workflow"] for c in ci),
                "pull_request_workflow_id_present": any(
                    c["id"] == KNOWN["pull_request_workflow"] for c in ci),
            }
    except (OSError, json.JSONDecodeError):
        pass

    baseline = {
        "schema": "yue2-rc6_1-baseline/1",
        "generated_at_utc": now,
        "mission": "RC6.1 — Developer Trust, Five-Metric Scientific Closure & Release Hardening (v1.0-rc2)",
        "git": {
            "local_repo": str(REPO),
            "branch": branch,
            "head": head,
            "head_subject": subject,
            "worktree_dirty": bool(dirty),
            "dirty_entries": dirty.splitlines()[:20],
            "head_matches_known_pr_head": head == KNOWN["pr_head_sha"],
            "base": KNOWN["base_sha"],
        },
        "github": gh_state,
        "runtime": {
            "generation_env": "ROCm 7.14.1 / torch 2.12.0+rocm7.14.1 (frozen sglang c67d541a40f8bf851e9fc1e925f5316638838cd6)",
            "effective_generation_runtime_sha256": "342b2f531b14a201b4aae1a6a14424bed7f03cd7f993c3a1c09657a6d6109051",
            "evaluator_envs_are_separate": True,
            "q3o_judge_env_recorded": "torch 2.10.0+rocm7.12.0 / transformers 4.57.6 (see rc5-q3o runtime receipt)",
            "note": "generation torch/ROCm is NOT the evaluator version; each evaluator env is re-verified in its own phase",
        },
        "scientific_baseline": {
            "campaign": "384/384 complete (192 prompts x 2), 0 failures, 0 retries, 5 truncated-but-valid",
            "historical_generation_pcm_identity": "380/384 FILE_BYTE_IDENTICAL; 4 CONTENT_IDENTITY_NOT_ESTABLISHED (historical FLAC absent)",
            "paper_reference": {"SongBench": 6.7316, "PER": 8.44, "MuLan": 0.5068,
                                "AllMusicCaps": 0.4054, "Q3O": 4.68},
            "scoreboard_A_S_T": {"SongBench": 6.736891, "PER": 17.769855, "MuLan": 0.509395,
                                 "AllMusicCaps": 0.405181, "Q3O": 4.393986, "Q3O_coverage": "192/192"},
            "scoreboard_B_S_V": {"SongBench": 6.742109, "PER": 8.448788, "MuLan": 0.504299,
                                 "AllMusicCaps": 0.403000, "Q3O": "NOT_RUN (RC6.1 must complete this)"},
            "per_attribution": {"T(S_T)": 17.769855, "V(S_T)": 9.585394, "T(S_V)": 20.204241,
                                "V(S_V)": 8.448788, "evaluator_path_effect_pp": -8.184461,
                                "selection_effect_pp": -1.136606,
                                "decomposition_order_dependent": True},
            "selection_reconciliation": {"changed_prompts": 60, "unchanged": 132,
                                         "removed": 60, "added": 60, "symmetric_difference": 120},
        },
        "key_rc6_gaps_this_mission_closes": [
            "V01-V10 verifier false-VERIFIED paths (M1)",
            "ASR identity partial-field acceptance + resume atomicity (M2)",
            "install pin drift + re-install not idempotent + workspace-local GPU lock + untargeted stop (M3)",
            "Scoreboard B Q3O missing (M4)",
            "fresh-workspace pilot / five-metric / cancel-resume not run (M5)",
            "VRAM 29.7 vs 47 GiB contradiction + percentile inconsistency (M6)",
        ],
    }

    # ---- resource preflight ----
    gpu = gpu_physical_identity()
    cg = cgroup_limits()
    rc, df = run(["df", "-h", "/data", "/workspace"])
    rc, mem = run(["free", "-b"])
    mem_line = mem.splitlines()[1].split() if mem else []
    rc, nproc = run(["nproc"])
    rc, vram = run(["cat", "/sys/class/drm/card1/device/mem_info_vram_total"])
    vram_used = run(["cat", "/sys/class/drm/card1/device/mem_info_vram_used"])
    lock = Path("/data/yue2/gpu.lock")
    lock_status = run([sys.executable, str(REPO / "scripts/gpu_lock.py"), "status"])[1]
    preflight = {
        "schema": "yue2-rc6_1-resource-preflight/1",
        "generated_at_utc": now,
        "gpu": gpu,
        "cgroup": cg,
        "host": {"nproc_visible": int(nproc) if nproc.isdigit() else None,
                 "free_total_bytes": int(mem_line[1]) if len(mem_line) > 1 else None,
                 "df": df},
        "gpu_vram_sysfs": {"card": "card1 (the single exposed render node)",
                           "total_bytes": vram[1] if vram else None,
                           "used_bytes": vram_used[1] if vram_used[1].isdigit() else None},
        "gpu_lock_now": (json.loads(lock_status) if lock_status.startswith("{") else lock_status[:400]),
        "processes_heavy": "checked at execution time (see 00_MISSION_LEDGER and run receipts)",
        "concurrency_policy": "single-owner GPU lock; all RC6.1 GPU work acquires the shared physical lock domain (M3.5)",
        "backup": {
            "second_volume": "/workspace/yue2-rc5-backup (18.55 GB checkpoints, frozen-tree verified)",
            "off_machine": "OFF_MACHINE_BACKUP_BLOCKED_EXTERNAL (no owner-authorized external store)",
        },
    }

    (OUT_DIR / "00_BASELINE.json").write_text(json.dumps(baseline, indent=1, ensure_ascii=False) + "\n")
    (OUT_DIR / "00_RESOURCE_PREFLIGHT.json").write_text(json.dumps(preflight, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"written": ["00_BASELINE.json", "00_RESOURCE_PREFLIGHT.json"],
                      "head": head, "github": gh_state.get("available"),
                      "gpu": {"bdf": gpu["exposed_bdf"], "uuid": gpu["exposed_unique_id"]},
                      "cgroup_mem_gib": cg.get("memory_limit_gib"),
                      "cpu_cores": cg.get("cpu_effective_cores")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
