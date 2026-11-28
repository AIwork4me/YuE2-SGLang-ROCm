# 05_CLI_CONTRACT.md — RC6 A5.3: the reference CLI contract

`scripts/reference_cli.py` (alias suggestion: `reference`). Thin orchestration
over proven tools — no reimplementation of reliable internals.

## Commands

| Command | Delegates to | GPU | Notes |
|---|---|---|---|
| `doctor` | `scripts/check_environment.py`, `scripts/gpu_identity.py verify` | optional | GPU checks run only when the venv exists; never silently skipped |
| `install` | `rc5_build_generation_env.sh`, `download_pins.py`, `rc5_install_sglang.sh`, `rc5_runtime_manifest.py` | no | pinned stack: torch 2.12.0+rocm7.14.1, sglang `c67d541a` + import-guard patches |
| `download` | `scripts/download_pins.py` | no | every file SHA256-verified; mirrors allowed only under hash verification |
| `generate` | `campaign_ops/run_with_server.sh` + `serve_yue2_rc5.sh` | **required** | single-owner lifecycle (lock→identity→ready→generate→verified stop) |
| `verify` | `scripts/rc6_verify_results.py` | no | verdict vocabulary below |
| `benchmark --mode pilot\|full` | `run_wsb.py` / `rc5_supervise.sh` | **required** | pilot = 5×2 official indices; full = 384 |
| `compare` | `rc6_verify_results.py --compare-reference` | no | reference scoreboard comparison with scope labels |
| `status` | — | no | workspace, repo HEAD, GPU lock, environments, models |
| `resume` | `rc5_supervise.sh` | **required** | crash-durable journal + checkpoints; refuses without a journal |
| `stop` | `scripts/gpu_lock.py stop --yes` | no | graceful SIGINT/SIGTERM to the recorded pid (never pkill/SIGKILL) |
| `package-evidence` | `rc5_backup.py verify` / `rc5_campaign_snapshot.py` | no | local evidence integrity + public-safe snapshot |

## Hard rules

1. **Exit codes**: `0` ok · `1` verification FAILED · `2` usage/env fatal ·
   `3` lock contention · `4` rejected (identity mismatch / no-clobber) ·
   `130` interrupted.
2. **GPU_REQUIRED by default**: GPU commands never fall back to CPU; the
   underlying tools are fail-loud (`gpu_identity.py` physical binding).
3. **No root, no global driver mutation**: install touches only the
   workspace venv; the host kernel driver is never modified.
4. **No-clobber**: `generate`/`benchmark` refuse non-empty output dirs;
   resume never rewrites a frozen journal.
5. **`--dry-run`**: prints the exact plan, executes nothing, labels output
   DRY-RUN — never counted as an execution.
6. **CWD-independent**: all paths resolve from the repo root; no reliance on
   the caller's CWD (fixes the historical `git -C ... apply` relative-path
   breakage).
7. **No un-authorized downloads**: only the SHA-pinned model/dataset set.
8. **Safe cancel**: Ctrl-C reaches the single lifecycle supervisor which
   drains and stops the server before releasing the lock.

## Self-check

```
python3 scripts/reference_cli.py --help
python3 scripts/reference_cli.py doctor --dry-run
python3 scripts/reference_cli.py status
```
