# RC4.1 — GitHub handoff (M6)

## Branch / PR / CI

- Branch: `mission/w7900-rc4-1-fail-loud-health-evidence`
  (created from `16f2504` = PR #17 head, drift-checked before branch)
- PR: **https://github.com/AIwork4me/YuE2-SGLang-ROCm/pull/18** (DRAFT,
  stacked; base `mission/w7900-rc4-repro-reliability`, head
  `mission/w7900-rc4-1-fail-loud-health-evidence`)
- Final pushed HEAD: **`c2dc61995fa48afabc6236c4f0766b20cbd47ce0`**
  (local == remote verified via git fetch after push)
- Exact-head CI: both `cpu-tests` workflows SUCCESS on this SHA:
  - https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/45090002171/job/137417183311
  - https://github.com/AIwork4me/YuE2-SGLang-ROCm/actions/runs/45089997300/job/137417167015
  - (first push 3f1046a failed CI: torch-less runners exposed a real
    contract gap — CPU-test authorization did not cover the no-torch
    branch; fixed in c2dc619 with a unit test; the failure is preserved
    in the run history, not hidden)
- Commits: 13 atomic commits on top of 16f2504 (M1 / M2 / M3×2 / M4×2 /
  M5×3 / reports / CSV-LF / CI-fix). No force-push; main untouched; no
  automated merges; PR #16/#17 untouched.

## Pre-push gates (all executed before each push)

`git diff --check` clean · tree clean · public-evidence guard PASS ·
lyrics detector PASS (469 files) · numeric-receipt integrity PASS ·
compileall + bash -n clean · full CI-scope suite green locally
(425/0/26) · mutation controls 12/12 KILLED.

## Evidence map

In-repo: `reports/w7900_rc4_1/**` (this tree).
Host-side (private, hashed): `/data/yue2-runs/rc4_1_evidence/
20261122T2300Z/` (phase A/B1/B2/C receipts, gpu-identity JSONs, frozen
manifests) and `/data/yue2-runs/rc4_1_native_pilot/` (official-protocol
artifacts incl. audio — CC BY-NC, NOT pushed).

## PR comment

Concise evidence summary posted to PR #18 (see PR timeline; long raw
logs stay host-side with SHA256-stable receipts).
