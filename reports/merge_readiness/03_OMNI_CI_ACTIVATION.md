# 03 — Omni CI activation handoff for sgl-project/sglang-omni#2540

Refreshed 2026-10-16 from live workflow YAML, branch ruleset and CI
permissions file. Nothing here is invented: every command, label and
permission below is verified against the current `main` (`2c23b68f`).

## 1. Exact blocked state (head `85ae4b73`)

Six workflows were created 2026-10-05T03:44Z and all sit at
**`action_required`** — GitHub's fork-PR "workflow awaiting approval" state.
Zero jobs executed. URLs:

- Lint — https://github.com/sgl-project/sglang-omni/actions/runs/37260615543
- Docs Check — https://github.com/sgl-project/sglang-omni/actions/runs/37260615542
- Test Layout — https://github.com/sgl-project/sglang-omni/actions/runs/37260615546
- CPU CI — https://github.com/sgl-project/sglang-omni/actions/runs/37260615550
- Omni CI — https://github.com/sgl-project/sglang-omni/actions/runs/37260615890
- XPU CI — https://github.com/sgl-project/sglang-omni/actions/runs/37260615544

This is **not** a lint failure, **not** a test failure and **not** a missing
label problem. Classification: GitHub `action_required` (mission category 5).
Additionally the PR carries no CI labels at all (category 4) — but labels
cannot be evaluated until the workflows are approved, because the approval
gate precedes label resolution.

## 2. What runs after approval (verified from workflow sources)

| Workflow | Trigger after approval | Gating |
|---|---|---|
| Lint (`lint.yaml`) | every PR, every push | none — unconditional; `pre-commit run --all-files` |
| Docs Check (`docs-check.yaml`) | opened/synchronize/reopened/ready_for_review | none |
| Test Layout (`test-layout.yaml`) | every PR | none |
| Omni CI (`omni-ci.yaml`) | PR events **and** labels | stage/model labels via `.github/scripts/resolve_ci_labels.py`; draft PRs blocked; `pr_ci_gate.py` additionally requires lint green + mergeable |
| CPU CI (`omni-cpu-ci.yaml`) | same label mechanism | `run-intel-cpu-ci` or `run-all-ci` |
| XPU CI (`omni-xpu-ci.yaml`) | same label mechanism | `run-intel-xpu-ci` or `run-all-ci` |

CI label vocabulary (from `resolve_ci_labels.py`): stage labels
`run-asr-ci`, `run-tts-ci`, `run-mps-ci`, `run-omni-ci`, `run-intel-cpu-ci`,
`run-intel-xpu-ci`, `run-mac-ci`, `run-all-ci`; model labels e.g.
`run-tts-higgs-tts-3-4b`, `run-tts-moss-tts-local-transformer-v1.5`,
`run-omni-qwen3-omni-30b-a3b-instruct`. **There is no YuE2 model label and
no YuE2 CI suite today.**

## 3. Branch ruleset (machine-enforced merge requirements)

From `repos/sgl-project/sglang-omni/rules/branches/main` (ruleset 14348408):

- Required status check: **`lint`** (only machine-required check).
- 1 approving review required; **extra approval required for unattributed
  changes** (i.e., if anyone other than the PR author pushes commits to the
  branch, an additional human approval is triggered — relevant to how the
  author integrates our PRs).
- Squash merge only; linear history; deletion/creation/non-fast-forward
  blocked.

## 4. Who can perform each action

| Action | Who | Verified from |
|---|---|---|
| Approve the six `action_required` workflows | any sglang-omni maintainer with write access (e.g., requested reviewer FrankLeeeee) | GitHub fork-approval mechanism |
| Add CI labels directly | maintainers with write access | GitHub label UI/API |
| Slash commands `/tag-run-ci-label`, `/rerun-failed-ci`, `/tag-and-rerun-ci` | only users in `.github/CI_PERMISSIONS.json`: Ccyest, CloudRipple, Ratish1, edwingao28, luojiaxuan, siju-samuel, zhaochenyang20 | `slash_command_handler.py` permission check |
| Author of the PR | cannot self-approve workflows, cannot self-label | fork + permission model |

The PR-template text mentioning `/tag-and-rerun-ci moss | qwen3-tts | …`
selectors predates the current label system; the *current* mechanism is the
stage/model-label vocabulary above, and slash commands were restored today
by main commit `2c23b68f` (#2873). **Do not blindly post model-selector
comments: no selector validates YuE2.**

## 5. Smallest appropriate CI set for this PR

1. **Approve and run: Lint, Docs Check, Test Layout.** CPU-only, minutes
   cheap, and `lint` is the sole required status check — this alone unblocks
   the machine gate (given a human review).
2. **Recommended additional: `run-tts-ci` (any model)** — YuE2 is served
   through the TTS/speech surface (`/v1/audio/speech`) and the PR touches
   `tests/unit_test/models/test_model_capabilities.py`, which other TTS
   models' suites may read. One TTS suite is enough; no need for all four.
3. **Not needed:** XPU CI (no XPU support claimed), ASR/MPS suites (no ASR/MPS
   surface touched), `run-all-ci` (wasteful).
4. **What CI cannot cover:** no suite executes YuE2 generation. Real
   validation is (a) the unit tests arriving with PR #1/#2
   (`test_yue2_platform_gates.py`, `test_yue2_speech_input_cap.py` — CPU
   runnable, no GPU needed) and (b) the author's focused H800 smoke test
   (report 05). If maintainers want a GPU-adjacent signal without YuE2 CI,
   the unit-test files can be invoked directly on any CI runner via the
   existing test-layout/CPU stages after integration.

## 6. Proposed maintainer request (concise, ready to post or adapt)

> @maintainer — all six workflows on this PR are `action_required` (fork-PR
> approval) since Oct 5; none has executed, so `lint` (the only required
> check) has no result. Could you approve the workflows — or at minimum
> Lint + Docs Check + Test Layout — and, if you want a serving-surface
> signal, add `run-tts-ci`? Note there is currently no YuE2 CI model label;
> YuE2-specific validation is the unit tests in the two companion PRs plus a
> focused H800 smoke test described in the evidence reports.

Post only once, from one account, after the author integrates the companion
PRs (report 04 defines the order). Do not group-ping.

## 7. Local pre-verification we can do (and did — see report 04)

`pre-commit run --all-files` equivalent against the integration preview on
CPU-only tooling, so the first maintainer-approved Lint run is green rather
than a second round-trip.

## Gate

`OMNI_CI_HANDOFF_READY` — blocked states classified from workflow YAML +
ruleset + permissions file; no commands invented; no irrelevant CI requested.
