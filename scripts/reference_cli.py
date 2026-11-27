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
sys.path.insert(0, str(REPO / "scripts"))
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


def ensure_frozen_upstream(sgl: Path, patch: Path, frozen: str, remote: str,
                           dry: bool = False,
                           log=print, sh_runner=None) -> tuple[int, str]:
    """M3.1/M3.3: transport-clone, then FETCH + verify the frozen commit,
    CHECKOUT the exact SHA, VERIFY HEAD, and apply the patch only when
    needed. Returns (exit_code, human_summary).

    Rules (fail-closed):
      * frozen SHA not obtainable -> FATAL (NO fallback to the branch head);
      * unexpected local modifications -> REJECT (never reset --hard);
      * already-applied patch -> skipped (idempotent);
      * neither-applies-nor-reverses patch -> REJECT (partially applied).
    """
    import subprocess as sp

    def run_silent(cmd):
        q = sp.run([str(c) for c in cmd], capture_output=True, text=True)
        return q.returncode, (q.stdout or "") + (q.stderr or "")

    if not sgl.exists():
        rc = (sh_runner or sh)(["git", "clone", "--branch", "add_yue2", "--quiet",
                                remote, str(sgl)], dry)
        if rc != 0:
            return EXIT_FATAL, "initial clone failed"
    if dry:
        return EXIT_OK, "DRY-RUN: frozen checkout/patch verification skipped"
    rc, _ = run_silent(["git", "-C", str(sgl), "fetch", "--quiet", remote])
    rc2, have = run_silent(["git", "-C", str(sgl), "cat-file", "-t", frozen])
    if rc2 != 0 or have.strip() != "commit":
        return EXIT_FATAL, (f"frozen upstream commit {frozen} not obtainable "
                            f"(fetch rc={rc}, cat-file rc={rc2}) — NO fallback "
                            "to the moving branch")
    if rc != 0:
        # the frozen commit is present LOCALLY (content-addressed objects);
        # the network refresh failed — proceed with the locally verifiable pin
        log(f"[reference] upstream refresh fetch failed (network); the frozen "
            f"commit {frozen[:12]} is present locally and pinned")
    rc, head = run_silent(["git", "-C", str(sgl), "rev-parse", "HEAD"])
    if head.strip() != frozen:
        rc, dirt = run_silent(["git", "-C", str(sgl), "status", "--porcelain"])
        if dirt.strip():
            return EXIT_REJECT, ("upstream worktree has unexpected local "
                                 "modifications; resolve manually (no reset --hard):\n"
                                 + dirt[:600])
        rc, _ = run_silent(["git", "-C", str(sgl), "checkout", "--quiet", frozen])
        if rc != 0:
            return EXIT_FATAL, f"checkout of frozen {frozen} failed"
    rc, head = run_silent(["git", "-C", str(sgl), "rev-parse", "HEAD"])
    if head.strip() != frozen:
        return EXIT_FATAL, f"HEAD {head.strip()[:12]} != frozen {frozen[:12]}"
    log(f"[reference] upstream verified at frozen head {frozen}")
    rc_rev, _ = run_silent(["git", "-C", str(sgl), "apply", "--reverse", "--check",
                            str(patch)])
    rc_fwd, _ = run_silent(["git", "-C", str(sgl), "apply", "--check", str(patch)])
    if rc_rev == 0:
        return EXIT_OK, "patch already applied — skipped (idempotent re-install)"
    if rc_fwd == 0:
        rc, out = run_silent(["git", "-C", str(sgl), "apply", str(patch)])
        if rc != 0:
            return EXIT_FATAL, f"patch apply failed: {out[:300]}"
        return EXIT_OK, "patch applied to the frozen tree"
    return EXIT_REJECT, ("patch neither applies cleanly nor reverses cleanly "
                         "(partially-applied or diverged tree); resolve manually")


def cmd_install(a) -> int:
    """Pinned environment: torch 2.12.0+rocm7.14.1 + sglang c67d541a + guards.

    RC6.1 M3.1/M3.3: the frozen upstream SHA is fetched + verified + checked
    out exactly; the import-guard patch is applied only when needed
    (idempotent re-install); a frozen SHA that cannot be obtained is a hard
    FAILURE with no silent fallback to the moving branch head.
    """
    W = ws(a)
    sgl = W / "upstream/sglang-latest"
    patch = REPO / "patches/rc5-0001-0003-0008-rocm-import-guards.patch"
    frozen = "c67d541a40f8bf851e9fc1e925f5316638838cd6"
    remote = "https://github.com/yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork.git"

    print("\n=== 3/5 upstream sglang c67d541a checkout (frozen PR #42106 head) ===")
    rc, summary = ensure_frozen_upstream(sgl, patch, frozen, remote, a.dry_run, print)
    if rc != EXIT_OK:
        print(f"[reference] FATAL/REFUSED: {summary}")
        return rc
    print(f"[reference] {summary}")
    steps = [
        ("1/5 generation venv (AMD index, hash-checked wheels)",
         ["bash", str(REPO / "scripts/campaign_ops/rc5_build_generation_env.sh")]),
        ("2/5 pinned models + dataset (SHA256-gated)",
         # M3.4: needs huggingface_hub — the GENERATION venv interpreter
         # (built in step 1), never the bare system python
         [str(W / "environments/generation/bin/python"),
          str(REPO / "scripts/download_pins.py"), "--workspace", str(W)]),
        ("5/5 install sglang (no-deps, no-build-isolation) + prove the imported runtime",
         ["bash", str(REPO / "scripts/campaign_ops/rc5_install_sglang.sh")]),
        ("5b/5 runtime manifest (audited-tree proof)",
         [str(W / "environments/generation/bin/python"),
          str(REPO / "scripts/rc5_runtime_manifest.py"),
          "--sglang-src", str(sgl), "--patch-file", str(patch),
          "--out", str(W / "logs/effective_runtime_manifest.json")]),
    ]
    for title, cmd in steps:
        print(f"\n=== {title} ===")
        rc = sh(cmd, a.dry_run, env={"YUE2_WORKSPACE": str(W),
                                     "YUE2_SGLANG_SRC": str(sgl)})
        if rc != 0:
            print(f"[reference] install step FAILED (rc={rc}): {title}")
            return EXIT_FATAL
    print("\n[reference] install complete (idempotent: re-running skips an "
          "already-applied patch and re-verifies every pin)")
    return EXIT_OK


def cmd_download(a) -> int:
    W = ws(a)
    venv = W / "environments/generation/bin/python"
    interp = str(venv) if venv.exists() else py()
    if not venv.exists():
        print("[reference] NOTE: generation venv not present yet — using the "
              "system interpreter (needs huggingface_hub); `reference install` "
              "builds the venv first")
    return sh([interp, str(REPO / "scripts/download_pins.py"), "--workspace", str(W)],
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
        # finalize the candidate bundle (lossless FLAC repack + model identity)
        # CPU-only; needs the generation venv interpreter (sglang importable)
        fin = [str(W / "environments/generation/bin/python"),
               str(REPO / "scripts/finalize_candidate.py"),
               str(out / "candidate_0"), str(out / "song.wav"),
               str(W / "models/YuE2-3B"), str(W / "models/YuE2-Vae-legacy")]
        print("[reference] finalizing candidate bundle (FLAC repack + identity)")
        frc = sh(fin, a.dry_run, env={"YUE2_WORKSPACE": str(W)})
        if frc != 0:
            print(f"[reference] finalize rc={frc} — bundle identity incomplete")
            rc = frc
        else:
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
    import gpu_lock
    lock_path = gpu_lock.resolve_default_lock()
    try:
        lock_state = json.loads(Path(lock_path).read_text()) if Path(lock_path).is_file() else None
    except (OSError, ValueError):
        lock_state = None
    print(json.dumps({
        "workspace": str(W),
        "repo_head": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                    capture_output=True, text=True).stdout.strip(),
        "gpu_lock_domain": {
            "lock": str(lock_path),
            "domain_name": gpu_lock.lock_domain_name(gpu_lock.resolve_physical_gpu()),
            "physical": gpu_lock.resolve_physical_gpu(),
            "protocol": "shared physical domain (BDF-keyed) across workspaces "
                        "when the lock root is commonly mounted",
        },
        "gpu_lock": lock_state,
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
    """M3.6 stop safety: the target is resolved in the SHARED physical lock
    domain, displayed BEFORE any signal, and REFUSED when ambiguous or when
    the live holder does not belong to the requested workspace/run.

    No pkill -f, no unscoped kill: only the recorded holder pid is signalled
    (graceful SIGINT/SIGTERM only), exactly as gpu_lock.graceful_stop does.
    """
    W = ws(a)
    import gpu_lock
    lock_path = gpu_lock.resolve_default_lock()
    st = gpu_lock.status(lock_path)
    holder = st.get("holder") or {}
    print(json.dumps({
        "requested_workspace": str(W),
        "lock_domain": str(lock_path),
        "domain_name": gpu_lock.lock_domain_name(gpu_lock.resolve_physical_gpu()),
        "holder": {k: holder.get(k) for k in ("who", "pid", "cmdline", "host",
                                              "acquired_at_utc")},
        "holder_live": st.get("holder_live"),
        "blocked": st.get("blocked"),
    }, indent=1))
    if not holder or not st.get("holder_live"):
        print("[reference] no live holder in this lock domain — nothing to stop")
        return EXIT_FAIL if holder else EXIT_OK
    cmd = holder.get("cmdline") or ""
    holder_ws = holder.get("workspace")
    belongs = (holder_ws is not None and str(W) == holder_ws) or \
              (holder_ws is None and str(W) in cmd)   # legacy receipt: cmdline only
    if a.workspace and not belongs:
        print(f"[reference] REFUSED: the live lock holder does not belong to "
              f"workspace {W} (holder workspace={holder_ws!r}). Inspect "
              f"the holder above; stopping another workspace's session "
              f"requires operating on that workspace explicitly.")
        return EXIT_REJECT
    if a.run_id and a.run_id not in cmd:
        print(f"[reference] REFUSED: the live holder does not match --run-id "
              f"{a.run_id!r} (holder who={holder.get('who')!r})")
        return EXIT_REJECT
    return sh([py(), str(REPO / "scripts/gpu_lock.py"), "--lock", str(lock_path),
               "stop", "--yes"], a.dry_run)


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
    st.add_argument("--run-id", default=None,
                    help="refuse to stop when the holder does not match this run id")
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
