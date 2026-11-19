# PR #12 — Independent Final CPU-only Freeze Audit (2026-11-16)

## Scope / Control

This is a **GitHub-code + synthetic CPU-test** review. The C2.1 Stacked Draft PR is based on PR #11. No live W7900, Arm A process, /data directory, benchmark audio, licensed lyrics, model weights, evaluator scoring or publication artifacts were modified. No auto-merge is authorized.

## Findings addressed

| Priority | Defect | Minimal fix | Negative control |
|---|---|---|---|
| P0 | Legacy journal row becomes falsely corrupt after same-candidate new retry | Accept only contiguous legacy prefix with a **later journaled new attempt for the same candidate**; preserve UNKNOWN, never promote old rows to verified | New row stripped of attempt fields creates an orphan COMPLETE receipt and fails; unmarked row after first new-format entry also fails |
| P0 | Result-only orphan was invisible to launched-only scan | Check unjournaled `*.result.json` without any launched peer | Orphan COMPLETE and FAILED both fail |
| P1 | Staging permissions default too broad for benchmark-derived audio | Private `0700` staging and audio dirs; final inherits restrictions | Test actual final permissions |
| P1 | Staging cleanup silently swallowed failure | Remove `ignore_errors=True`, disclose cleanup failure while final remains absent | Inject deterministic PermissionError, verify warning and private residue |
| P1 | Final audit write or candidate copy I/O could evade cleanup | Route both through existing private-stage Abort | Synthetic ENOSPC on `.package_audit.json` |

## Provenance integrity limitation

The legacy prefix boundary is inferred from **append order and schema**, not from a signed migration receipt. The checker now distinguishes legitimate old-failure/new-retry from a damaged record whose new-style result is left orphaned, but cannot cryptographically establish the authenticity of an editable pre-C2 journal. Every legacy record remains `LEGACY_PROVENANCE_INCOMPLETE`. Do not upgrade historical evidence to `BYTE_HASH_VERIFIED`.

## Required exact-head validation

- All expected CPU GitHub checks pass at the final PR #12 head.
- The 8 new tests are collected and pass, including real subprocess file operations; no fixture includes licensed audio/text.
- Existing public evidence guard, numeric invariant and protocol lock checks remain green.
- New release-grade Tier 2 on real WSB data remains **NOT_TESTED** in GitHub Actions.

## Freeze decision (independent engineering review)

- **C2.1 security/correctness:** GO for Owner Review **only after exact-head CI success**.
- **CPU-only implementation:** GO to freeze **only after exact-head CI success and owner acceptance of the documented legacy evidence limitation**.
- **Full YuE2 ROCm Publication:** NO-GO: G3 close(), G10 AR/HIP fault, G15 rights/history and G20 live provenance remain unresolved; Arm A/B benchmark has not been accepted.

Do not deploy or merge this stacked driver into active Arm A. Preserve PR #8/#9/#10/#11 ownership and base relationships. No force push.
