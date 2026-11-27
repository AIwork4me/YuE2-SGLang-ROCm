#!/usr/bin/env python3
"""reference_cli.py — the YuE2-on-ROCm Developer Reproduction Reference CLI.

One discoverable entry point over the verified tools (thin orchestration
only — every subcommand delegates to a proven script; no reimplementation):

  reference doctor        environment + optional GPU compute diagnostic
  reference install       pinned ROCm/sglang environment (RC5 frozen stack)
  reference download      SHA256-verified model/dataset pins
  reference generate      one song (GPU) under the single-owner lifecycle
  reference verify        verify YOUR results (GPU identity/audio/provenance)
  reference benchmark     --mode pilot | full (WildSongBench)
  reference compare       compare your numbers with the reference scoreboard
  reference status        runs, journals, GPU lock state
  reference resume        resume a paused/interrupted campaign (GPU)
  reference stop          graceful stop of the GPU lock holder
  reference package-evidence  local evidence package + hashes

Hard rules (05_CLI_CONTRACT.md):
  * exit codes: 0 ok · 1 verification FAILED · 2 usage/environment fatal ·
    3 lock contention · 4 rejected (identity/no-clobber)
  * GPU operations are GPU_REQUIRED — CPU fallback never happens silently
  * outputs never overwrite existing files (no-clobber; new run_ids only)
  * --dry-run prints the plan, executes nothing, and is labelled DRY-RUN
  * no root, no global driver mutation, no un-authorized downloads
  * works from any CWD (all paths resolved from the repo root)

Usage:
  python3 scripts/reference_cli.py <command> --help
  alias reference='python3 /path/to/repo/scripts/reference_cli.py'
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_WS = Path(os.environ.get("YUE2_WORKSPACE", "/data/yue2"))
EXIT_OK, EXIT_FAIL, EXIT_FATAL, EXIT_LOCK, EXIT_REJECT = 0, 1, 2, 3, 4


def sh(cmd: list[str], dry: bool, cwd: Path | None = None, env: dict | None = None) -> int:
    printable = " ".join(str(c) for c in cmd)
    print(f"[reference] $ {printable}" + ("   (DRY-RUN)" if dry else ""))
    if dry:
        return EXIT_OK
    e = dict(os.environ)
    if env:
        e.update({k: str(v) for k, v in env.items()})
    p = subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None, env=e)
    return p.returncode


def py() -> str:
    return sys.executable


def ws(a) -> Path:
    return Path(a.workspace)


def add_common(ap: argparse.ArgumentParser):
    ap.add_argument("--workspace", default=str(DEFAULT_WS),
                    help=f"workspace root (default {DEFAULT_WS})")
    ap.add_argument("--dry-run", action="store_true", help="print the plan only")


# ---------------------------------------------------------------- commands

def cmd_doctor(a) -> int:
    """Portable diagnostic (CPU ok); GPU compute check when the venv exists."""
    steps: list[tuple[str, list[str]]] = []
    steps.append(("environment diagnostic", [py(), str(REPO / "scripts/check_environment.py")]))
    venv = ws(a) / "environments/yue2-gfx1100/bin/python"
    if venv.exists():
        steps.append(("GPU identity + compute (fail-loud)",
                      [str(venv), str(REPO / "scripts/gpu_identity.py"), "verify",
                       "--expect-arch", a.expect_arch]))
    else:
        print("[reference] generation venv not present yet — GPU checks run after "
              "`reference install` (documented, not silently skipped)")
    for title, cmd in steps:
        print(f"\n=== {title} ===")
        rc = sh(cmd, a.dry_run)
        if rc not in (0,):
            print(f"[reference] doctor step FAILED (rc={rc}): {title}")
            return EXIT_FAIL
    return EXIT_OK


def cmd_install(a) -> int:
    """Pinned environment: torch 2.12.0+rocm7.14.1 + sglang c67d541a + guards."""
    W = ws(a)
    steps = [
        ("1/4 generation venv (AMD index, hash-checked wheels)",
         ["bash", str(REPO / "scripts/campaign_ops/rc5_build_generation_env.sh")]),
        ("2/4 pinned models + dataset (SHA256-gated)",
         [py(), str(REPO / "scripts/download_pins.py"), "--workspace", str(W)]),
        ("3/4 upstream sglang c67d541a + import-guard patches",
         ["bash", str(REPO / "scripts/campaign_ops/rc5_install_sglang.sh")]),
        ("4/4 prove the imported runtime IS the audited tree",
         [str(W / "environments/generation/bin/python"),
          str(REPO / "scripts/rc5_runtime_manifest.py"),
          "--sglang-src", str(W / "upstream/sglang-latest"),
          "--patch-file", str(REPO / "patches/rc5-0001-0003-0008-rocm-import-guards.patch"),
          "--out", str(W / "logs/effective_runtime_manifest.json")]),
    ]
    for title, cmd in steps:
        print(f"\n=== {title} ===")
        rc = sh(cmd, a.dry_run, env={"YUE2_WORKSPACE": str(W)})
        if rc != 0:
            return EXIT_FATAL if not a.dry_run else EXIT_OK
    return EXIT_OK


def cmd_download(a) -> int:
    return sh([py(), str(REPO / "scripts/download_pins.py"), "--workspace", str(ws(a))],
              a.dry_run)


def cmd_generate(a) -> int:
    """One song on the GPU under the single-owner lifecycle supervisor."""
    W = ws(a)
    out = Path(a.out_dir).resolve()
    if out.exists() and any(out.iterdir()):
        print(f"[reference] REFUSED: output directory not empty: {out} "
              f"(no-clobber; choose a fresh --out-dir)")
        return EXIT_REJECT
    lyr = Path(a.lyrics)
    if not lyr.is_file():
        print(f"[reference] FATAL: lyrics file missing: {lyr}")
        return EXIT_FATAL
    request = {
        "style": Path(a.style).read_text() if Path(a.style).is_file() else a.style,
        "lyrics": lyr.read_text(),
        "seed": a.seed,
        "output_path": str(out),
        "output_file_name": "song.wav",
        "artifacts_dir": str(out / "candidate_0"),
        "id": a.song_id,
        "cot": "full", "ode_steps": 32, "semantic_max_tokens": 9000,
        "abc_max_tokens": 4096, "vae_core_frames": 1024, "vae_halo_frames": 16,
    }
    req_file = out / "request.json"
    if not a.dry_run:
        out.mkdir(parents=True, exist_ok=True)
        req_file.write_text(json.dumps(request, indent=1, ensure_ascii=False) + "\n")
    cmd = ["bash", str(REPO / "scripts/campaign_ops/run_with_server.sh"),
           "--log-dir", str(W / "logs"), "--",
           "curl", "-sS", "-X", "POST", "http://127.0.0.1:31000/v1/audio/generations",
           "-H", "Content-Type: application/json",
           "--data-binary", f"@{req_file}"]
    env = {"YUE2_WORKSPACE": str(W), "YUE2_SERVE_SCRIPT": "scripts/serve_yue2_rc5.sh"}
    rc = sh(cmd, a.dry_run, env=env)
    if rc == 0 and not a.dry_run:
        print(f"[reference] verify with: python3 scripts/reference_cli.py verify "
              f"--run-dir {out}")
    return rc


def cmd_verify(a) -> int:
    cmd = [py(), str(REPO / "scripts/rc6_verify_results.py"),
           "--run-dir", str(Path(a.run_dir).resolve())]
    if a.json_out:
        cmd += ["--json-out", str(Path(a.json_out).resolve())]
    return sh(cmd, a.dry_run)


def cmd_benchmark(a) -> int:
    W = ws(a)
    if a.mode == "pilot":
        run_dir = Path(a.run_dir or (W / "runs/rc6-pilot")).resolve()
        if run_dir.exists() and (run_dir / "journal.jsonl").exists():
            print(f"[reference] REFUSED: pilot run dir already has a journal: {run_dir}")
            return EXIT_REJECT
        cmd = ["bash", str(REPO / "scripts/campaign_ops/run_with_server.sh"),
               "--log-dir", str(W / "logs"), "--",
               py(), str(REPO / "scripts/run_wsb.py"), "--runs", str(run_dir),
               "--indices", "0", "1", "2", "79", "81", "--run-id",
               a.run_id or "rc6-pilot-5x2"]
    elif a.mode == "full":
        run_dir = Path(a.run_dir or (W / "runs/rc6-full")).resolve()
        cmd = ["bash", str(REPO / "scripts/campaign_ops/rc5_supervise.sh"),
               str(run_dir), a.run_id or f"rc6_full_{time.strftime('%Y%m%dT%H%M%SZ')}"]
    else:
        print(f"[reference] FATAL: unknown mode {a.mode}")
        return EXIT_FATAL
    env = {"YUE2_WORKSPACE": str(W), "YUE2_SERVE_SCRIPT": "scripts/serve_yue2_rc5.sh"}
    return sh(cmd, a.dry_run, env=env)


def cmd_compare(a) -> int:
    cmd = [py(), str(REPO / "scripts/rc6_verify_results.py"),
           "--run-dir", str(Path(a.run_dir).resolve()), "--compare-reference"]
    if a.json_out:
        cmd += ["--json-out", str(Path(a.json_out).resolve())]
    return sh(cmd, a.dry_run)


def cmd_status(a) -> int:
    W = ws(a)
    print(json.dumps({
        "workspace": str(W),
        "repo_head": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                    capture_output=True, text=True).stdout.strip(),
        "gpu_lock": json.loads(W.joinpath("gpu.lock").read_text())
        if W.joinpath("gpu.lock").is_file() else None,
        "environments": sorted(p.name for p in (W / "environments").glob("*"))
        if (W / "environments").is_dir() else [],
        "models": sorted(p.name for p in (W / "models").glob("*"))
        if (W / "models").is_dir() else [],
    }, indent=1))
    return EXIT_OK


def cmd_resume(a) -> int:
    W = ws(a)
    run_dir = Path(a.run_dir).resolve()
    if not (run_dir / "journal.jsonl").is_file():
        print(f"[reference] FATAL: no journal at {run_dir} — nothing to resume")
        return EXIT_FATAL
    cmd = ["bash", str(REPO / "scripts/campaign_ops/rc5_supervise.sh"), str(run_dir),
           a.run_id or "resumed"]
    return sh(cmd, a.dry_run, env={"YUE2_WORKSPACE": str(W)})


def cmd_stop(a) -> int:
    return sh([py(), str(REPO / "scripts/gpu_lock.py"), "stop", "--yes"], a.dry_run)


def cmd_package(a) -> int:
    W = ws(a)
    run_dir = Path(a.run_dir).resolve()
    cmd = [py(), str(REPO / "scripts/rc5_backup.py"), "verify", "--run-dir", str(run_dir)]
    if a.snapshot:
        cmd = [py(), str(REPO / "scripts/rc5_campaign_snapshot.py"),
               "--run-dir", str(run_dir), "--out", str(Path(a.snapshot).resolve())]
    return sh(cmd, a.dry_run, env={"YUE2_WORKSPACE": str(W)})


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reference",
                                 description="YuE2 on ROCm Developer Reproduction Reference CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="environment + GPU diagnostic")
    add_common(d)
    d.add_argument("--expect-arch", default="gfx1100")
    d.set_defaults(fn=cmd_doctor)

    i = sub.add_parser("install", help="pinned ROCm/sglang environment")
    add_common(i)
    i.set_defaults(fn=cmd_install)

    dl = sub.add_parser("download", help="SHA256-verified pins")
    add_common(dl)
    dl.set_defaults(fn=cmd_download)

    g = sub.add_parser("generate", help="generate one song (GPU, lifecycle-supervised)")
    add_common(g)
    g.add_argument("--lyrics", required=True, help="path to a lyrics text file")
    g.add_argument("--style", default="[Tags]\nsoft pop\n", help="style string or file")
    g.add_argument("--seed", type=int, default=831001)
    g.add_argument("--out-dir", required=True)
    g.add_argument("--song-id", default="first_song")
    g.set_defaults(fn=cmd_generate)

    v = sub.add_parser("verify", help="verify your generation results")
    add_common(v)
    v.add_argument("--run-dir", required=True)
    v.add_argument("--json-out", default=None)
    v.set_defaults(fn=cmd_verify)

    b = sub.add_parser("benchmark", help="WildSongBench pilot/full (GPU)")
    add_common(b)
    b.add_argument("--mode", choices=["pilot", "full"], required=True)
    b.add_argument("--run-dir", default=None)
    b.add_argument("--run-id", default=None)
    b.set_defaults(fn=cmd_benchmark)

    c = sub.add_parser("compare", help="compare with the reference scoreboard")
    add_common(c)
    c.add_argument("--run-dir", required=True)
    c.add_argument("--json-out", default=None)
    c.set_defaults(fn=cmd_compare)

    s = sub.add_parser("status", help="workspace/run/lock status")
    add_common(s)
    s.set_defaults(fn=cmd_status)

    r = sub.add_parser("resume", help="resume an interrupted campaign (GPU)")
    add_common(r)
    r.add_argument("--run-dir", required=True)
    r.add_argument("--run-id", default=None)
    r.set_defaults(fn=cmd_resume)

    st = sub.add_parser("stop", help="graceful stop of the GPU lock holder")
    add_common(st)
    st.set_defaults(fn=cmd_stop)

    pe = sub.add_parser("package-evidence", help="verify/package run evidence")
    add_common(pe)
    pe.add_argument("--run-dir", required=True)
    pe.add_argument("--snapshot", default=None, help="optional public snapshot output")
    pe.set_defaults(fn=cmd_package)
    return p


def main() -> int:
    p = build_parser()
    a = p.parse_args()
    try:
        return a.fn(a)
    except KeyboardInterrupt:
        print("[reference] interrupted (exit 130)")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
