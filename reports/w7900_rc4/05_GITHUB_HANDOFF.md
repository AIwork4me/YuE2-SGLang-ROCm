# RC4 M5.4 — GitHub Handoff

Date: 2026-11-22/23 (UTC).

## Delivery

- Branch: `mission/w7900-rc4-repro-reliability`
- Base: `mission/joint-blog-rc2` @ `48d1cb6` (verified live PR #16 head; stacked PR)
- **PR #17 (DRAFT): https://github.com/AIwork4me/YuE2-SGLang-ROCm/pull/17**
- Head SHA pushed: `01a79950e2309acfadc641b1272321fd1fc18cea`
- Commits (7, atomic): `af1dd25` M0/M4 baseline+tie+truncation ·
  `0f44eae` M1/M2 tooling · `957cd2d` M1/M2 evidence · `b9bcd27` M4.5/M5 docs ·
  `42ac023` finalize-interpreter fix · `21c803d` M2/M3 deliverables ·
  `01a7995` final receipts/format
- No force-push; `main` untouched; PR #15/#16 untouched; no external messages.

## Pre-push checks (all executed)

`git diff --check` clean · `git status` clean · full diff reviewed ·
applicable tests run (CI-scope 367/0 + suites) · restricted-data scan
(tier-1 + tier-2 guards PASS on final tree).

## Post-push verification

- `git fetch origin`; remote branch SHA == local (`01a7995…`).
- PR diff inspected via API (files = reports/w7900_rc4/*, scripts fixes,
  tests, docs — exactly the intended set).
- Exact-HEAD CI: two workflow runs launched on `01a7995`
  (runs 45075550586, 45075583925); final status recorded below.
- Final evidence summary comment posted on PR #17.

## CI status (exact head `01a7995`)

- `cpu` (run 45075550586 / job 137371852424): **completed success** ✅
- `cpu` (run 45075583925 / job 137371957538): **completed success** ✅
  (both observed green on 2026-11-23; if re-run later, re-verify at the URLs
  above — local suites are never a substitute for the exact-HEAD check)

## Evidence file map (all under reports/w7900_rc4/ on this branch)

00 environment/git/plan · 01 fresh-clone report+receipts+provenance+
controls+verdict · 02 runtime RCA+matrix+memory+verdict · 03 performance
raw/summary/envelope/concurrency/verdict · 04 tie/truncation/provenance/
public-evidence audits · 05 review/CI/gates/handoff · FINAL_REPORT_ZH.

Host-side raw evidence (not committed, per policy): /data/yue2-runs/rc4_evidence/
(R1 captures, reliability CSVs, probes, window states) and /data/rc4/ws/
(fresh workspace + logs). Hash-pinned; paths recorded for the owner.
