# Phase 0/1 review responses (author)

## PHASE0_REVIEW findings -> resolution
- P1 environment.json/check_environment.py destroyed by workspace swap: RESTORED,
  checker re-run by independent reviewer (exit 0, no blockers). 
- P2 github.com "blocked" wording: CORRECTED to "intermittent" (measured both
  outcomes); http:// transport + API fallbacks documented.
- P2 ffmpeg version: CORRECTED to 6.1.1.
- P2 insteadOf config: FIXED (--add; both rewrites verified in global config).
- P2 HF endpoint: CORRECTED - machine presets HF_ENDPOINT=hf-mirror.com; all
  artifacts hash-verified against official pins (phase3_download_manifest.json).
- P2 api_git.py mirror: COPIED to scripts/api_git.py.
- P2 chassis disclosure: ADDED (8x 1002:744b on host, 1 exposed; W7900D SKU note).
- P2 apt 403 vs 503: CORRECTED.
- P2 uncommitted: RESOLVED by this commit.

## PHASE1_REVIEW findings -> resolution
- P1 setup script could not fresh-install (guard treated absent torch as fatal):
  FIXED (exit-code 2 = absent -> proceed).
- P1 nothing committed/pushed: RESOLVED by this commit.
- P2 Config A/B mischaracterization: REPORT REWRITTEN - torch._rocm_init
  auto-activates venv userspace at import; ldd-based "25 host libs" was a static
  artifact. Runtime measurement (this commit's evidence JSON): plain import maps
  61 unique venv libs, 0 host libs.
- P2 unsourced "375/5" numbers: REPLACED by measured unique-.so lists in
  evidence/gfx1100/phase1_torch_environment.json.
- P2 LD_LIBRARY_PATH disclosure: ADDED (container presets /opt/rocm/lib; our
  scripts never set it).
