# YuE2 on NVIDIA + AMD ROCm — Author Integration Handoff

> Prepared 2026-10-17. This document describes contributions available for the author's `add_yue2` branches; it does **not** claim they are merged into upstream SGLang or SGLang-Omni.

## Summary

Three reviewable compatibility PRs and two standalone SGLang-Omni lint commits are ready for the YuE2 author's integration. AMD evidence covers SGLang and SGLang-Omni on Radeon PRO W7900 (gfx1100), plus SGLang on Radeon 8060S (gfx1151). Full-dataset generation and later integrated-code smoke verification refer to **different, explicitly pinned source trees**.

## Three compatibility PRs

| Contribution | Target / current state (2026-10-17) | Head SHA | Purpose |
|---|---|---|---|
| [Omni ROCm #1](https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1) | `yiakwy-xpu-ml-framework-team/sglang-omni:add_yue2` · **Open** | [`eca7770f`](https://github.com/AIwork4me/sglang-omni/commit/eca7770fe196fe970f7d847858a5f92444b75538) | ROCm reference execution path, preserving existing CUDA optimizations |
| [Omni Long-Lyrics #2](https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/2) | `yiakwy-xpu-ml-framework-team/sglang-omni:add_yue2` · **Open** | [`4c089d19`](https://github.com/AIwork4me/sglang-omni/commit/4c089d193f1186aeb40609ac4913273db9cdea95) | Model-specific acceptance of valid full-song lyric inputs |
| [Original SGLang ROCm #1](https://github.com/yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork/pull/1) | `yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork:add_yue2` · **Open** | [`def437fb`](https://github.com/AIwork4me/sglang/commit/def437fb7949f26bd1b06473882fd928757c6377) | ROCm compatibility fallback for the separate original SGLang YuE2 integration |

The two Omni PRs target the author branch at `85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9`; the original SGLang PR targets its own author base at `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`. **Do not mix their repositories or histories.**

## Two SGLang-Omni lint commits

| Order | Commit | Scope | Recorded validation |
|---|---|---|---|
| 1 | [`ae11c6ad`](https://github.com/AIwork4me/sglang-omni/commit/ae11c6ad246023494a4f55f89e852384e019f5b4) | Mechanical formatting / upstream pre-commit cleanup | Part of the validated integration preview |
| 2 | [`b91b95440`](https://github.com/AIwork4me/sglang-omni/commit/b91b95440cf3ce9b6d83f6593d85c91aadffbfd2) | Naming-policy closure: 172 → 0 reported violations; 58 symbols renamed, 7 narrow exceptions | 76/76 focused tests, repo-wide pre-commit, real W7900 short-audio smoke; recorded SHA256 match against pre-rename smoke |

**Dependency:** `b91b95440` is a direct descendant of `ae11c6ad`. Apply both after the two Omni compatibility PRs, **in that order**. Test statements are based on the [recorded integration handoff](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/40bd59f94079345917b526a3e2ee49c8a9f1f867/reports/final_merge_closure/10_FINAL_MERGE_HANDOFF.md).

## Exact Omni integration sequence (previously rehearsed)

**Scope:** author `sglang-omni:add_yue2` at **`85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9`**. Refresh GitHub PR heads and check whether any commits are already integrated before reusing these commands. If the author base has advanced, revalidate the merge; do not assume the prior zero-conflict result still holds.

```bash
# In the author's sglang-omni checkout. Start on add_yue2.
git switch add_yue2
git rev-parse HEAD  # previously rehearsed base: 85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9

# Step 1: ROCm reference path (Omni PR #1).
git fetch https://github.com/AIwork4me/sglang-omni.git eca7770fe196fe970f7d847858a5f92444b75538
git merge --no-ff FETCH_HEAD

# Step 2: full-song lyrics (Omni PR #2).
git fetch https://github.com/AIwork4me/sglang-omni.git 4c089d193f1186aeb40609ac4913273db9cdea95
git merge --no-ff FETCH_HEAD

# Step 3: mechanical style layer.
git fetch https://github.com/AIwork4me/sglang-omni.git ae11c6ad246023494a4f55f89e852384e019f5b4
git cherry-pick FETCH_HEAD

# Step 4: naming-policy closure (depends on Step 3).
git fetch https://github.com/AIwork4me/sglang-omni.git b91b95440cf3ce9b6d83f6593d85c91aadffbfd2
git cherry-pick FETCH_HEAD

# Inspect final tree and status before any author-owned push:
git rev-parse HEAD^{tree}
git status --short
```

This sequence was rehearsed in an isolated worktree on the pinned base: **zero conflicts**, integrated **tree `363073e688fa9761c72f029a1022a87405b1aead`**, equal to the tested `b91b95440` tree, with the focused suite **76/76 passed**. The author decides how to merge and push; no author-owned branch is modified by this handoff.

The **original SGLang** ROCm contribution is a [separate PR](https://github.com/yiakwy-xpu-ml-framework-team/AMD-sglang-benchmark-fork/pull/1), not a commit to cherry-pick into `sglang-omni`.

## AMD evidence — what was actually tested

| Hardware and stack | Scope | Main result |
|---|---|---|
| W7900 · original SGLang | Independent full WildSongBench, 192 prompts × 2 candidates | 384/384 strict audit; selected-arm SongBench Global Avg **6.736** |
| W7900 · SGLang-Omni | Independent full WildSongBench, **`bench/omni-wsb` @ `c4841f0c`** | 384/384 strict audit; selected-arm SongBench Global Avg **6.732** |
| Radeon 8060S (gfx1151) · original SGLang | Independent full WildSongBench | 384/384 strict audit; selected-arm SongBench Global Avg **6.683** |
| W7900 · SGLang-Omni final combined tree | Separate 76-test + local lint + real short-audio smoke | PASS; **not** a repeat 384-candidate run |

**Full-run source fidelity:** the W7900 Omni 384/384 run used the `c4841f0c` benchmark tree (a ROCm PR #1 development revision plus benchmark-only artifact instrumentation). The two Prompt-164 candidates required a separately documented temporary input-cap exemption. It did **not** run on the later combined tree with PR #2 and the style commits.

Serving evidence on W7900 Omni: GPU **BS=1**; client concurrency **C=1/2/4/8**; C=1 BS=1 P50 E2E latency **217.3 s** for mean **223 s** output audio, real-time multiplier **1.030×**, conventional client E2E RTF **0.975**; throughput approximately **0.0046 requests/s** across C=1/2/4/8. Client concurrency did not demonstrate GPU batching or throughput scaling.

Full reproducibility details are in the public [README](https://github.com/AIwork4me/YuE2-SGLang-ROCm), the [evidence index](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/main/docs/EVIDENCE_INDEX.md), [W7900 Omni scoring report](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/author_acceptance/OMNI_WILDSOGNBENCH_GFX1100.md) and [corrected serving report](https://github.com/AIwork4me/YuE2-SGLang-ROCm/blob/137ce40d9ad6886885040f69a4742bb8b4e658bd/reports/final_acceptance/SERVING_PERFORMANCE_CORRECTION.md).

**Suggested author action:** Please review and integrate the three compatibility PRs and the two ordered Omni lint commits into the respective `add_yue2` branches when convenient. Our goal is to make the existing YuE2 integrations reviewable for the [official Omni PR #2540](https://github.com/sgl-project/sglang-omni/pull/2540) and [official SGLang PR #42106](https://github.com/sgl-project/sglang/pull/42106). Their final upstream merge is still pending.
