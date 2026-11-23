#!/usr/bin/env python3
"""mutation_controls_rc41.py — RC4.1 M5.2 mutation controls.

Applies each mutation to the working tree (git-restored afterwards), runs
the targeted test battery, and records KILLED / SURVIVED. A SURVIVED
mutation is a gap in the test battery and must be closed or explicitly
accepted with rationale — never hidden.

Usage: python3 scripts/mutation_controls_rc41.py [--quick]
Requires a clean git tree (safety: restore is `git checkout --`).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                          **kw)


def git_restore(paths: list[str]):
    sh(["git", "checkout", "--"] + paths)


MUTATIONS: list[dict] = [
    {
        "id": "M1", "desc": "remove GPU device guard (mismatch -> ok)",
        "file": "scripts/gpu_identity.py",
        "old": 'receipt["status"] = "GPU_DEVICE_MISMATCH"',
        "new": 'receipt["status"] = "GPU_IDENTITY_VERIFIED"',
        "tests": ["tests/test_gpu_identity.py"],
        "limit": 3,  # only mutate the first occurrences (arch + cuda build)
    },
    {
        "id": "M2", "desc": "downgrade GPU mismatch to warning (ok=True)",
        "file": "scripts/gpu_identity.py",
        "old": 'f"{expected_arch!r}")\n        receipt["ok"] = False\n        return _finish(receipt, receipt_path)\n    if expected_bdf',
        "new": 'f"{expected_arch!r}")\n        receipt["ok"] = True\n        return _finish(receipt, receipt_path)\n    if expected_bdf',
        "tests": ["tests/test_gpu_identity.py"],
    },
    {
        "id": "M3", "desc": "dead scheduler returns READY",
        "file": "scripts/server_readiness.py",
        "old": "    if not facts[\"scheduler_alive\"]:",
        "new": "    if False:",
        "tests": ["tests/test_server_readiness.py"],
    },
    {
        "id": "M4", "desc": "readiness only checks HTTP /health",
        "file": "scripts/server_readiness.py",
        "old": "    if not ident_ok:",
        "new": "    if False:",
        "tests": ["tests/test_server_readiness.py"],
    },
    {
        "id": "M5", "desc": "gpu_lock released immediately after acquire",
        "file": "scripts/gpu_lock.py",
        "old": "    try:\n        yield receipt",
        "new": "    try:\n        fcntl.flock(fd, fcntl.LOCK_UN)\n        yield receipt",
        "tests": ["tests/test_run_with_server.py::test_5_gpu_lock_held_for_whole_session"],
    },
    {
        "id": "M6", "desc": "skip server cleanup on wrapper exit",
        "file": "scripts/campaign_ops/run_with_server.sh",
        "old": "on_exit() {\n  local grc=\"${GATEWAY_RC:-$?}\"\n  stop_server",
        "new": "on_exit() {\n  local grc=\"${GATEWAY_RC:-$?}\"\n  true",
        "tests": ["tests/test_run_with_server.py::test_2_driver_failure_still_stops_server"],
    },
    {
        "id": "M7", "desc": "repeated-tags timeout made unbounded (inf)",
        "file": "scripts/rc4_reliability_matrix.py",
        "old": 's, d, b, e = post(args.server, p, 60.0)',
        "new": 's, d, b, e = post(args.server, p, float("inf"))',
        "tests": ["tests/test_input_budget.py::test_timeouts_bounded"],
    },
    {
        "id": "M8", "desc": "delete input validity checks (always OK)",
        "file": "scripts/input_budget.py",
        "old": '    def reject(cls, reason, **measured):\n        receipt["class"] = cls',
        "new": '    def reject(cls, reason, **measured):\n        receipt["class"] = cls\n        return',
        "tests": ["tests/test_input_budget.py"],
    },
    {
        "id": "M9", "desc": "mix an old run row into the evidence CSV",
        "file": "reports/w7900_rc4/03_PERFORMANCE_RAW.csv",
        "old": None, "new": None,  # special: duplicate the first data row
        "tests": ["tests/test_evidence_consistency_rc41.py"],
    },
    {
        "id": "M10", "desc": "cite 791 rows as 790 in the final report",
        "file": "reports/w7900_rc4/FINAL_REPORT_ZH.md",
        "old": "原始数据 791 行",
        "new": "原始数据 790 行",
        "tests": ["tests/test_evidence_consistency_rc41.py"],
    },
    {
        "id": "M11", "desc": "wrong GB/GiB conversion (51.5 'GiB')",
        "file": "reports/w7900_rc4/03_RESOURCE_ENVELOPE.md",
        "old": "51.5 decimal GB (= 47.98 GiB)",
        "new": "51.5 GiB",
        "tests": ["tests/test_evidence_consistency_rc41.py"],
    },
    {
        "id": "M12", "desc": "stale PENDING reintroduced in verdict JSON",
        "file": "reports/w7900_rc4/01_REPRODUCIBILITY_VERDICT.json",
        "old": "superseded by RC4.1 evidence reconciliation",
        "new": "PENDING re-check later",
        "tests": ["tests/test_evidence_consistency_rc41.py"],
    },
]


def apply(m: dict) -> bool:
    p = REPO / m["file"]
    if m["id"] == "M9":
        lines = p.read_text().splitlines(keepends=True)
        # duplicate the first data row (an 'old run' mixed in)
        lines.insert(1, lines[1])
        p.write_text("".join(lines))
        return True
    text = p.read_text()
    if m["old"] not in text:
        print(f"    [apply] pattern not found in {m['file']}")
        return False
    if m.get("limit"):
        text = text.replace(m["old"], m["new"], m["limit"])
    else:
        text = text.replace(m["old"], m["new"])
    p.write_text(text)
    return True


def main() -> int:
    st = sh(["git", "status", "--porcelain"])
    dirty = [l for l in st.stdout.splitlines()
             if not l.startswith("??")]
    if dirty:
        print("REFUSING: working tree not clean (tracked changes present)")
        return 2
    results = []
    for m in MUTATIONS:
        print(f"[{m['id']}] {m['desc']}")
        try:
            if not apply(m):
                results.append({**m, "result": "NOT_RUN",
                                "reason": "mutation pattern not found"})
                continue
            r = sh([PY, "-m", "pytest", "-q", "--timeout=600"]
                   + m["tests"]) if False else sh(
                [PY, "-m", "pytest", "-q"] + m["tests"], timeout=900)
            killed = r.returncode != 0
            results.append({**m, "result": "KILLED" if killed else "SURVIVED",
                            "pytest_rc": r.returncode,
                            "tail": r.stdout.strip().splitlines()[-1]
                            if r.stdout.strip() else ""})
            print(f"    -> {'KILLED' if killed else 'SURVIVED'} "
                  f"(pytest rc={r.returncode})")
        finally:
            git_restore([m["file"]])
    out = {
        "receipt_type": "rc4_1_mutation_controls",
        "executed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                         time.gmtime()),
        "results": [{"id": r["id"], "desc": r["desc"], "file": r["file"],
                     "result": r["result"],
                     **({"reason": r["reason"]} if "reason" in r else
                        {"pytest_rc": r.get("pytest_rc"),
                         "tail": r.get("tail", "")})}
                    for r in results],
    }
    summary = {r["id"]: r["result"] for r in results}
    out["summary"] = summary
    dest = REPO / "reports/w7900_rc4_1/05_CI_GPU_MUTATION_RESULTS.raw.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1) + "\n")
    survived = [r["id"] for r in results if r["result"] == "SURVIVED"]
    print(json.dumps(summary, indent=1))
    print(f"survived: {survived or 'none'}; raw: {dest}")
    return 0 if not survived else 1


if __name__ == "__main__":
    raise SystemExit(main())
