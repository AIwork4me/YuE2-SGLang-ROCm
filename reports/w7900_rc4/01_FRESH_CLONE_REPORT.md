# RC4 M1 — Fresh-Clone End-to-End Developer Reproduction

Date: 2026-11-22. Executor: RC4 mission session (same host, same operator
tooling — see verdict caveat). Fresh clone:
`/data/rc4/fresh_clone/YuE2-SGLang-ROCm` @ `48d1cb6` (verified live PR #16
HEAD). Isolated workspace: `/data/rc4/ws` (local /data-class disk, 940+ GiB
free; NOT the near-full NFS `/workspace`, NOT the campaign workspace
`/data/yue2`, NOT the campaign output paths, NOT any project-local venv).

## Reproduction modes

- **Mode A (verified local asset cache)**: models/VAE/dataset/evaluator
  assets copied from the campaign workspace, then **every** pinned file
  SHA256-verified by the project's own gates (`download_pins.py` ALL PINS
  VERIFIED; `fetch_eval_assets_hub.py` verify_assets OK: 56 pinned files).
  Byte-identity is guaranteed by the pins, not assumed from the copy.
- **Mode B (fully clean acquisition)**: attempted and partially executed —
  code clone (full), both venvs from public indexes (full), evaluator tree
  rebuilt from the pinned tarball through the hash-gated patch chain (full),
  evaluator venvs rebuilt (in progress at report time; uv proxy stalls
  documented), dataset metadata re-downloaded and hash-matched (full), model
  weights/evaluator model assets (7.8 G + 12.4 G) NOT re-downloaded due to
  mirror throughput — hash-verified cache copies instead. **Claim:
  PARTIAL Mode B.** No unverified cache was reused anywhere.

## Executed developer journey (command → receipt in 01_COMMAND_RECEIPTS.jsonl)

1. Clone at pinned commit — ✅ HEAD == `48d1cb6`
2. `check_environment.py` — ✅ BLOCKERS none, WARNINGS none
3. Pin/materialize workspace — ✅ ALL PINS VERIFIED
4. Environment A (native torch 2.10.0+rocm7.1) — ✅ built fresh; pip check
   clean. **Defect found (M1.5)**: documented manual commands omit TMPDIR;
   pip temp exhausted `/tmp` → fail. Documented in QUICKSTART §0.
5. Frozen evaluator dependencies — ✅ tree rebuilt with per-stage hash gates;
   venv build in progress (network-bound; honest PENDING if unfinished).
6. Environment B (SGLang ROCm) — ✅ built fresh incl. editable sglang from
   the freshly patched pinned source; GPU-validated stack asserts.
7. Real GPU smoke — **defect found then fixed**: `run_smoke_test.sh`
   activated a stale `environments/yue2` path (reproduced: exit 2, "No such
   file or directory"). Fixed (YUE2_VENV resolution + repo-relative phase0
   script); re-run → **SMOKE PASS** on W7900D (fp32/fp16/bf16 finite, yue2
   imports).
8. Native full song — ✅ `rc4_pilot_armA` 2/2 complete (694.9 s / 620.5 s;
   audio 191.3 s / 154.8 s; official seeds; artifacts complete). A live
   SIGTERM interruption mid-run exercised quarantine + verified resume-skip
   (candidate regenerated).
9. SGLang full song — ✅ `rc4_pilot_armB` 2/2 complete (635.5 s total,
   peak VRAM 47.1 GiB), identity-verified server stop rc=0, VRAM released.
   **Defect found then fixed**: running `run_wsb.py` under host python
   wastes a full generation then fails at finalize (sglang import);
   fail-fast guard added + QUICKSTART documents the Env B interpreter.
10. Output audio validity — ✅ ffprobe-valid FLAC (48 kHz stereo) both paths;
    auditor verified 2/2 artifacts per run.
11. WSB pilot — ✅ both paths (2 candidates, prompt 0, official seeds).
12. Pilot audit `--mode pilot` — ✅ verdict PILOT, problem_count 0 (both).
    **Defect found then fixed**: auditor flagged the torch driver's
    in-place quarantine dirs as "unexpected candidate directory" — resumed
    runs could never pass audit; auditor now recognizes quarantined
    partials as evidence (regression suite green).
13. Pilot scoring — ⏳ evaluator venv build (network-bound) — see verdict.
14. Scored candidate count / selection — pending 13.
15. Identity-verified shutdown — ✅ (receipt-based stop, "gone after
    SIGINT", rc=0; port freed; VRAM → 28 MB).
16. GPU lock/process release — ✅ verified after every window.

## Negative controls

`01_NEGATIVE_CONTROLS.md` — NC1…NC10 all fail-closed; NC5 produced a
robustness fix (receipt field validation); NC8 exposed the host HF_* env
override hazard (documented in QUICKSTART).

## Deviations and environment-specific findings (all documented, none hidden)

- Host git wrapper clones via gh-proxy (content verified by commit hash).
- huggingface.co unreachable from urllib → hf-mirror per machine policy
  (hash-verified either way).
- Host-wide HF_HOME/HF_HUB_CACHE override per-command exports (NC8).
- uv stalls on large PyPI wheels through the egress proxy → pip fallback.
- Tool-session process-group kills exercised the drivers' graceful-stop
   paths three times — each time state proved resume-safe (positive
   evidence for M2 interruption guarantees, from real interruptions).

## Verdict

See `01_REPRODUCIBILITY_VERDICT.json`.
