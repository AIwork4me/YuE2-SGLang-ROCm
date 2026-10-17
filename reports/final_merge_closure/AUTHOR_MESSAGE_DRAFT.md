# Draft message to the YuE2 author (for USER review — do not send automatically)

Hi — thanks for the YuE2 ports in sglang-omni#2540 and sglang#42106. All of
the remaining mechanical upstream-gate work is prepared and verified; the
only thing left that we can't do is push to your branches. Two independent
items, each cherry-pickable in one command:

## 1. sglang-omni #2540 — close the last Lint blocker (naming policy)

Your add_yue2 head 85ae4b733 currently fails the repo's leading-underscore
policy (172 findings; policy landed in #2267/#2338/#2365 before the PR was
opened). We prepared and fully verified the closure:

- Merge your PRs #1 (eca7770f, ROCm reference path) and #2 (4c089d19, long
  lyrics) into add_yue2.
- Then cherry-pick two commits from our fork:
  - ae11c6ad — mechanical pre-commit style layer (whitespace/isort/black).
  - b91b95440 — public-naming closure: 58 renames across the yue2 files,
    with framework names kept under narrowly-scoped noqa (your transformers
    _init_weights hook, the ATen _flash_attention_forward op, and the
    _yue2_fp8_originals marker that your quantization.py sets).
- Both are single commits on top of each other; the exact commands are in
  report 06 of the evidence package (link below).

What we verified so you don't have to rediscover it: the rename diff is
identifier-only (AST-proven), all 76 unit tests pass, the full pre-commit
suite is green repo-wide, and on a physical W7900D the seeded smoke request
produces bit-identical WAV output before and after the rename. Collision
traps that a mechanical rename would have hit (self.capture bool,
causal_mask local, offload_ar parameter) were avoided deliberately.

After you push, the remaining steps are maintainer-side: approve the
workflows (Lint/Docs Check/Test Layout), one focused H800 smoke (no NVIDIA
run exists yet on any integrated commit — checklist ready), and a review.
Everything else (W7900D end-to-end, 384/384 WildSongBench, serving sweep,
long-lyrics validation) is already documented in the evidence repo.

## 2. sglang #42106 — three blockers, all prepared

a) Lint: cherry-pick AIwork4me/sglang@fix/yue2-upstream-lint
   (1a9f2d92, parent = your ced0ef7d): fixes the six failing hooks with the
   PR's own pinned toolchain; the live "mot" module key is untouched.
b) Conflict: merging current main touches only registry.py — keep both
   your "m-a-p/yue2-3b": "YuE2Pipeline" line and main's renamed
   fastvideo-fasth3-8-step-v2 entry; resolution file ready.
c) run-ci: the finish-gate jobs fail only on the missing label — a
   maintainer comment /tag-run-ci-label (or the run-ci label) unblocks it.

Evidence package (branch handoff/yue2-final-merge-blocker-closure in
AIwork4me/YuE2-SGLang-ROCm): live status, rename map + machine-readable
inventory, lint/test/GPU results, the bit-identity proof, the end-to-end
integration rehearsal, independent reviews, and the H800 checklist.

Happy to adjust any of the renames — they're organized as one focused
commit exactly so you can review or rework them in one pass.
