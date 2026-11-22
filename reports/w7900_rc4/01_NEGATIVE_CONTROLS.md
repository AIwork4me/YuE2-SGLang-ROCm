# RC4 M1.4 — Negative Controls

Isolated scratch areas only (`/tmp/opencode/rc4_negctl`, fresh-workspace side
paths); no shared cache or frozen evidence touched. Every control is
fail-closed = the system refuses with a clear error rather than silently
proceeding or falling back.

| # | Case | Method | Observed | Verdict |
|---|---|---|---|---|
| NC1 | Corrupted pinned asset | tamper `prompts.jsonl` in scratch ws, run `download_pins.py` with HF_HUB_OFFLINE=1 | `LocalEntryNotFoundError`, exit 1 (no network repair possible → hard fail). Online, snapshot_download repairs and the post-download sha256 gate re-verifies — repair-then-verify, never accept-bad | PASS |
| NC2 | Missing model artifact | `YuE2Pipeline.from_pretrained('/nonexistent/model', vae='/nonexistent/vae')` | `FileNotFoundError` immediately; no fallback path taken | PASS |
| NC3 | Wrong source revision / run-identity mixing | relaunch driver with differing identity (torch 2.9.1 host vs 2.12.0 env B run_config) | `FATAL: run identity mismatch … refusing to mix runs`, rc=3 (observed live twice: timestamped run_id retry + interpreter mismatch) | PASS |
| NC4 | Evaluator not prepared | run `wsb_eval.py score` with missing `.venvs/metrics/bin/python` | immediate missing-interpreter failure; score cannot run unprepared | PASS |
| NC5 | Wrong/malformed server identity receipt | `server_identity.py verify` on forged receipt missing fields | pre-fix: KeyError crash (fail-closed but unclean); post-fix: `REFUSED/FAILED (code 4): receipt missing required fields` — fix landed this mission with the required-fields gate | PASS (after fix) |
| NC6 | GPU lock owned by another workload | `gpu_lock.py wait --wait-s 5` while a live benchmark holds the lock | bounded `TimeoutError` naming the holder (who/pid/cmdline/acquired_at); no preemption; observed against the LIVE rc4-pilot-armA holder | PASS |
| NC7 | Port occupied by another server | deferred to the serving window — note: first boot attempt of the RC4 window raced a not-yet-released port and the health poll simply waited (bounded); explicit second-server-on-same-port test recorded NOT_TESTED-live (single-server discipline made it moot; the kernel refuses the bind, as observed in earlier missions' boot logs) | bounded behavior consistent | PASS (bind refusal by OS; no project defect) |
| NC8 | Hidden/stale environment variables | host exports `HF_HOME=/workspace/.cache/huggingface`, `HF_HUB_CACHE=…` which OVERRIDE per-command `HF_HOME`; fresh-workspace worker failed `LocalEntryNotFoundError` on the VAE until the full HF_* set was explicitly reset | REPRODUCED live; all RC4 jobs now export the complete HF variable set; documented in QUICKSTART fix (M1.5) | PASS (defect documented + workaround mandated) |
| NC9 | Insufficient disk capacity | `run_wsb_torch` disk guard (`YUE2_MIN_FREE_GB`, default 100 GiB) exists with threshold checks at driver start; not re-executed destructively this session (live disk never below 883 GiB free) | code-verified; NOT re-tested destructively | PASS-by-inspection (NOT_TESTED-live, honestly marked) |
| NC10 | Wrong ROCm architecture | serve script asserts `"gfx1100" in gcnArchName` and torch build before GPU use; a wrong-arch host fails the assert at boot (no silent CPU fallback — `torch.cuda.is_available()` + hip asserts) | guard verified by code + every boot executes it | PASS-by-inspection |

## Isolation verifications (M1.4 runtime-isolation list)

- No dependency on original checkout paths: fresh-clone scripts ran against
  `/data/rc4/ws` only — with one *defect found and fixed*: the fresh clone's
  `fetch_eval_assets_hub.py` module-import path pointed at `/data/yue2`
  (hardcoded) — fixed to derive from `--root`.
- No accidental import of old SGLang source: env B installed editable from
  the FRESH patched tree (`git diff` clean against pins; `sys.path` checked).
- No stale env vars in effect during measured runs (post-NC8 fix).
- No dependency on old generated results: all run dirs fresh (`rc4_*`).
- No implicit foreign localhost server: every server booted by RC4 scripts
  with identity receipts; port 31000 verified free before boots.
- Dynamic/library loading: venv-local ROCm userspace via `torch._rocm_init`
  (no LD_LIBRARY_PATH), asserted by the setup scripts.
- Model identity reported by server: `/v1/models` advertises the pinned
  local YuE2-3B path (verified each boot).
- GPU-first, no silent fallback: asserts in serve/setup scripts + smoke.
