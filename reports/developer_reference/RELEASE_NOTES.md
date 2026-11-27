# RELEASE_NOTES.md — Developer Reproduction Reference v1.0-rc1

**Prepared 2026-11-27 (RC6). NOT PUBLISHED** — a Release Candidate is
prepared, not released: no GitHub Release, no tag, no joint-publication
claim without owner (and, for joint validation, author/AMD) authorization.

## What this is

The YuE2-on-ROCm **Developer Reproduction Reference**: everything a
developer needs to install, generate, verify, benchmark, diagnose and
recover the official YuE2 music-generation stack on a Radeon PRO W7900
(gfx1100) under ROCm — with every scientific claim bound to machine-
readable evidence and every external approval honestly absent until it
exists.

## Headline capabilities (all verified on hardware in RC6)

1. **Golden path**: `python3 scripts/reference_cli.py doctor / install /
   generate / verify / benchmark / compare / status / resume / stop` —
   one-command per step, fail-closed, no-clobber, dry-run support.
2. **First song, verified**: original publishable lyrics included; the
   generated song verifies `VERIFIED_REFERENCE_RUN` (model + runtime +
   config + audio integrity + lifecycle cleanliness).
3. **Fresh-clone reproduction (Mode 2)**: fresh checkout + fresh venv +
   fresh workspace reproduces the exact pinned runtime identity
   (`yue2_runtime_sha256 342b2f53…`) and a byte-identical same-seed song.
4. **Scientific closure**: determinism (380/384 + PCM-level honesty),
   evaluator identity contracts + fail-closed resume (20 negative
   controls + live control), the 2×2 PER attribution (dominant factor
   −8.18 pp engine path; corrected arm 8.4488% vs paper 8.44%), corrected
   Scoreboard B executed with the frozen official evaluator, Q3O boundary
   (repeatability ≠ equivalence, tie-rate denominators exact).
5. **Performance reference**: single consolidated, unit-disciplined
   envelope (P50 275.27 s; RTF 1.2866; Q3O 42.41 GiB peak) with
   methodology and scope.
6. **Hand-off packages**: author review package (A01–A12), AMD engineering
   package (AMD01–AMD10), CUDA PER/Q3O runbooks with pre-registered
   criteria, independent-runner task, upstream patch ownership plan.

## Known limitations (headline; full list in docs/KNOWN_LIMITATIONS.md)

- PER's official engine (vLLM 0.14.0) and Q3O's official engine have no
  ROCm builds — disclosed substitutions, separate arms, no equivalence
  claims.
- SGLang YuE2 support is unmerged upstream (pinned PR snapshot).
- Single-GPU serialization; CUDA-only fast paths fall back to reference
  implementations (author's native capability gates).
- Off-machine backup, CUDA comparisons, author and AMD acceptance:
  BLOCKED_EXTERNAL / NOT_PRESENT (never faked).

## Compatibility

PHYSICAL_PASS: W7900/W7900D 48 GiB (gfx1100). PARTIAL_PHYSICAL_PASS
(historical): Radeon 8060S. EXPECTED_BUT_UNVERIFIED: RX 7900 XTX (Q3O
NOT_TESTED below the measured 42.4 GiB judge peak), RX 9070 XT.
NOT_TESTED: everything else. Same-arch ≠ verified.

## Upgrade / support policy

One verified pinned stack at a time (`configs/developer.lock.yaml` +
MAINTENANCE_SCHEMAS.json update procedures). Anything else is
UNSUPPORTED_CONFIGURATION and the verification tool says so.
