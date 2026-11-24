#!/usr/bin/env python3
"""Mutation controls for the RC5 Q3O MoE placement blocks.

Each control applies ONE arithmetic mutation to a copy of
scripts/rc5_q3o_moe.py and runs tests/test_rc5_q3o_moe.py against it in a
temporary tree. A mutation is KILLED when at least one test fails. The
unmutated module must pass every test in the same environment (baseline
control) or the run aborts with rc 2. Mutations are source-text
replacements that must occur exactly once in the module.

Usage:
  python3 scripts/mutation_controls_q3o_moe.py --python <interpreter> \
      [--label environment-label] [--out report.json]

Run on the accelerator host with the GPU free (the GPU block tests are the
interesting half); a CPU-only run (accelerators hidden by the caller) is also
valid and is recorded as such via the environment probe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE = "scripts/rc5_q3o_moe.py"
TESTS = "tests/test_rc5_q3o_moe.py"

MUTATIONS = [
    ("R1_no_topk_normalisation", "top-k weights not normalised to sum 1",
     "if norm_topk_prob:", "if False:"),
    ("R2_bf16_softmax", "softmax computed in bf16 instead of fp32",
     "routing_weights = F.softmax(router_logits, dim=1, dtype=torch.float)",
     "routing_weights = F.softmax(router_logits, dim=1, dtype=torch.bfloat16)"),
    ("R3_stock_torch_topk", "plain torch.topk: tie-breaking not pinned (nondeterministic at "
     "boundary ties on torch 2.10.0+rocm7.14.1)",
     "order = torch.argsort(routing_weights, dim=-1, descending=True, stable=True)",
     "order = torch.topk(routing_weights, k, dim=-1).indices"),
    ("R4_unstable_argsort", "argsort without stable=True: tie order not pinned",
     "descending=True, stable=True)", "descending=True)"),
    ("G1_gate_up_swapped", "gate and up projections swapped (GPU block)",
     "gate, up = gu.chunk(2, dim=-1)", "up, gate = gu.chunk(2, dim=-1)"),
    ("G2_routing_weight_not_bf16", "routing weights kept in fp32 (GPU block)",
     "w.to(torch.bfloat16).unsqueeze(-1)", "w.unsqueeze(-1)"),
    ("G3_no_routing_weight", "routing weights dropped (GPU block)",
     "(out * w.to(torch.bfloat16).unsqueeze(-1)).sum(dim=0)", "out.sum(dim=0)"),
    ("G4_weights_assigned_to_wrong_experts", "weight matrix flipped along the top-k axis (GPU block)",
     "w.scatter_add_(0, selected.t().contiguous(), rw_bf16.t().contiguous().to(torch.float32))",
     "w.scatter_add_(0, selected.t().contiguous(), rw_bf16.flip(-1).t().contiguous().to(torch.float32))"),
    ("G5_unselected_experts_leak", "unselected experts get weight 1e-3 instead of 0 (GPU block)",
     "w = torch.zeros(E, T, dtype=torch.float32, device=selected.device)\n"
     "        w.scatter_add_(0, selected.t().contiguous(),",
     "w = torch.full((E, T), 1e-3, dtype=torch.float32, device=selected.device)\n"
     "        w.scatter_add_(0, selected.t().contiguous(),"),
    ("C1_no_bf16_rounding", "all intermediate bf16 rounding removed (CPU block)",
     "return x.to(torch.bfloat16).to(torch.float32)", "return x"),
    ("C2_router_logits_not_bf16", "router logits not rounded to bf16 (CPU block)",
     "router_logits = _bf16(F.linear(x, self.gate_w))", "router_logits = F.linear(x, self.gate_w)"),
    ("C3_gate_up_swapped", "gate and up projections swapped (CPU block)",
     "gate, up = F.linear(state, self.gate_up[e]).chunk(2, dim=-1)",
     "up, gate = F.linear(state, self.gate_up[e]).chunk(2, dim=-1)"),
    ("C4_no_routing_weight", "routing weights dropped (CPU block)",
     "_bf16(out * rw_f[tok, k, None])", "_bf16(out)"),
    ("C5_silu_dropped", "activation function removed (CPU block)",
     "F.silu(_bf16(gate))", "_bf16(gate)"),
    ("C6_silu_output_not_rounded", "silu output not rounded to bf16 before the product (CPU block)",
     "_bf16(_bf16(F.silu(_bf16(gate))) * _bf16(up))", "_bf16(F.silu(_bf16(gate)) * _bf16(up))"),
    ("C7_wrong_weight_slot", "routing weight of the neighbouring top-k slot used (CPU block)",
     "rw_f[tok, k, None]", "rw_f[tok, (k + 1) % self.top_k, None]"),
]

PROBE = ("import torch, json; print(json.dumps({'torch': torch.__version__, "
         "'hip': torch.version.hip, 'gpu': bool(torch.cuda.is_available()), "
         "'device': (torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)}))")


def run_tests(python: str, tree: Path, junit: Path):
    env = dict(os.environ)
    env.setdefault("YUE2_WORKSPACE", "/data/yue2")
    return subprocess.run(
        [python, "-m", "pytest", TESTS, "-q", "--no-header", "-p", "no:cacheprovider",
         "-ra", "--strict-markers", f"--junitxml={junit}"],
        cwd=tree, env=env, capture_output=True, text=True, timeout=1800)


def parse_junit(junit: Path):
    root = ET.parse(junit).getroot()
    names, failing = [], []
    for tc in root.iter("testcase"):
        name = f"{tc.get('classname', '').replace('.', '.')}::{tc.get('name', '')}"
        names.append(name)
        if tc.find("failure") is not None or tc.find("error") is not None:
            failing.append(name)
    return names, failing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--python", required=True, help="interpreter that has torch (and pytest)")
    ap.add_argument("--label", default="", help="environment label recorded in the report")
    ap.add_argument("--out", help="write the JSON report here")
    args = ap.parse_args()

    src = (REPO / MODULE).read_text()
    module_sha = hashlib.sha256(src.encode()).hexdigest()
    test_sha = hashlib.sha256((REPO / TESTS).read_bytes()).hexdigest()
    probe = subprocess.run([args.python, "-c", PROBE], capture_output=True, text=True)
    try:
        env_info = json.loads(probe.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        env_info = {"error": (probe.stderr or probe.stdout)[-300:]}

    rows, killed = [], 0
    with tempfile.TemporaryDirectory(prefix="rc5_q3o_moe_mut_") as tmp:
        tmp = Path(tmp)
        (tmp / "scripts").mkdir(parents=True)
        (tmp / "tests").mkdir(parents=True)
        shutil.copy(REPO / TESTS, tmp / TESTS)
        junit = tmp / "junit.xml"
        (tmp / MODULE).write_text(src)                      # baseline control
        proc = run_tests(args.python, tmp, junit)
        _, failing = parse_junit(junit)
        baseline = {"returncode": proc.returncode, "failing_tests": failing}
        if proc.returncode != 0 or failing:
            print(f"::error::baseline control failed: rc={proc.returncode} {failing}", file=sys.stderr)
            print(proc.stdout[-2000:], file=sys.stderr)
            return 2
        for mid, desc, old, new in MUTATIONS:
            n = src.count(old)
            if n != 1:
                print(f"::error::mutation {mid}: pattern occurs {n} times (expected 1)", file=sys.stderr)
                return 2
            (tmp / MODULE).write_text(src.replace(old, new))
            proc = run_tests(args.python, tmp, junit)
            _, failing = parse_junit(junit)
            is_killed = proc.returncode != 0 or bool(failing)
            killed += int(is_killed)
            rows.append({"id": mid, "description": desc, "killed": is_killed,
                         "returncode": proc.returncode, "failing_tests": failing})
            print(f"{'KILLED  ' if is_killed else 'SURVIVED'} {mid}: {failing}", flush=True)
            (tmp / MODULE).write_text(src)

    report = {
        "schema": "yue2-rc5-q3o-moe-mutation/1",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "module": MODULE, "module_sha256": module_sha,
        "test_file": TESTS, "test_file_sha256": test_sha,
        "environment": {"label": args.label or Path(args.python).name, "python": args.python, **env_info},
        "baseline": baseline,
        "mutations": rows,
        "summary": {"killed": killed, "total": len(rows),
                    "survivors": [r["id"] for r in rows if not r["killed"]]},
        "notes": "Source-text mutations, one per control, each pattern occurring exactly once. "
                 "The contribution summation dtype (fp32 vs sequential bf16) is a disclosed deviation "
                 "of both blocks and is deliberately NOT covered by a mutation control.",
    }
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(f"report written to {args.out}")
    print(json.dumps(report["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
