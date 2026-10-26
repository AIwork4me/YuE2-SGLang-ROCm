# 06 — Author Merge Handoff (merge-readiness mission, 2026-10-26)

Prepared for **yiakwy-xpu-ml-framework-team** (author of `add_yue2` in both
sgl-project/sglang#42106 and sgl-project/sglang-omni#2540). Nothing below
modifies your branches; everything is cherry-pickable/mergeable from the
AIwork4me forks with exact SHAs. All validation was performed on AMD
Radeon 8060S (gfx1151) + ROCm, with CUDA semantics preserved and verified
by independent review (reports 01–03, `reviews/`).

## A. Original SGLang — PR #42106

**Everything you need is on one branch:**
`AIwork4me/sglang @ integration/yue2-sglang-gfx1151-merge-ready`
(head `44c8fa51f`, pushed 2026-10-26). It contains, in order:

| Step | Commit | What it is | Your authorship |
|---|---|---|---|
| base | `ced0ef7d` chain | your `add_yue2` (3 commits) | untouched |
| +1 | merge `def437fb` | ROCm capability guards = fork PR #1 head, **entered as a merge** | PR #1 preserved verbatim |
| +2 | `6b368483f` | pre-commit lint pass = your-requested `1a9f2d92` (cherry-pick) | original author/date kept |
| +3 | merge `5ef99013a` | latest upstream `main` (as of 2026-10-26), all conflicts resolved | — |
| +4 | `bcb496ab9`,`44c8fa51f` | route-loader path fix + independent-review P0/P1 fixes + formatting | small, fully documented |

Suggested one-liner for you:

```bash
git fetch https://github.com/AIwork4me/sglang.git integration/yue2-sglang-gfx1151-merge-ready
git merge --no-ff FETCH_HEAD   # on add_yue2; or cherry-pick the 3 small fix commits over the same sequence
```

What the branch already solved for you (details in report 01):

1. **Conflicts vs current main** — `registry.py` (keep your yue2 line, adopt
   main's renamed fastvideo entries), `.codespellrc` (union), `experimental/`
   flattening (your standalone files now at top-level `yue2/`, router moved
   into `multimodal_gen/runtime/entrypoints/yue2_api.py` so wheel installs
   keep working), test relocated to main's `test/registered/unit/` layout.
2. **Kernels-namespace rule** (P0): main now enforces
   `kernels/ops/*.py == {__init__.py}` (`test_kernels_namespace.py`, applied
   to this very kernel in #41349) — your vendored wrapper moved verbatim
   (git mv) to `srt/models/yue2/_deep_select.py`; `fastpath.py` imports it
   from there. NVIDIA behavior unchanged (review B: fast-path ASTs
   identical to your code).
3. **CI registration** (P0): the gate test now carries `register_cpu_ci`
   like its neighbors, so `run_suite.py` collects it.
4. Validated on gfx1151 end-to-end: 121/121 tests, real server, real audio
   (report 02), with **no environment-variable disables** — the capability
   gates choose paths themselves.

**Separate (NOT in the branch, offered for independent main PRs):** a
4-file ROCm host-boot overlay for main itself (sgl_kernel/aiter import
guards; `patches/sglang_main_rocm_host_boot_overlay.patch`) — main HEAD
today cannot even `import sglang` on a HIP host without CUDA wheels.

**Still yours:** resolve `main` conflicts on the PR if you prefer your own
route; ask a maintainer for the `run-ci` label (all current red checks are
that label gate plus the lint this branch fixes); one H800 smoke of the
integrated head per `08_H800_REQUIRED_VALIDATION.md` (from the prior
closure package; still valid).

## B. SGLang-Omni — PR #2540

The four-step sequence from
`docs/YUE2_UPSTREAM_AUTHOR_HANDOFF.md` was **re-verified bit-exact today**
on your unchanged base `85ae4b73` (integrated tree
`363073e688fa9761c72f029a1022a87405b1aead`, zero conflicts), plus:

- 39/39 focused tests pass on gfx1151 (platform gates, naming-policy
  regression, long-lyrics speech-cap including the WildSongBench
  prompt-164 cases);
- omni's own lint surface green (ruff 0.11.10 / isort 5.13.2 /
  black 24.10.0 pins) on all changed files;
- a fresh integration preview against **latest omni main** (`b6299238` at
  build time; 381 commits past your merge base) is on
  `AIwork4me/sglang-omni @ integration/yue2-omni-merge-ready` — see
  report 03 for its construction and validation. Only one file touched
  both sides (`tests/unit_test/models/test_model_capabilities.py`).

Suggested sequence for you (unchanged from the prior handoff, now with the
main-merge preview available if you want it whole):

```bash
# on add_yue2 @ 85ae4b73
git fetch https://github.com/AIwork4me/sglang-omni.git eca7770fe196fe970f7d847858a5f92444b75538 && git merge --no-ff FETCH_HEAD
git fetch https://github.com/AIwork4me/sglang-omni.git 4c089d193f1186aeb40609ac4913273db9cdea95 && git merge --no-ff FETCH_HEAD
git fetch https://github.com/AIwork4me/sglang-omni.git ae11c6ad246023494a4f55f89e852384e019f5b4 && git cherry-pick FETCH_HEAD
git fetch https://github.com/AIwork4me/sglang-omni.git b91b95440cf3ce9b6d83f6593d85c91aadffbfd2 && git cherry-pick FETCH_HEAD
# optionally then:
git fetch https://github.com/AIwork4me/sglang-omni.git integration/yue2-omni-merge-ready && git merge --no-ff FETCH_HEAD
```

## C. Merge order (both repos)

1. (SGLang) cherry-pick/merge the integration branch — or run its 4 steps
   yourself in the same order; then request `run-ci` and one H800 smoke.
2. (Omni) steps 1–4 on `add_yue2`, optionally + the main-merge preview.
3. (Upstream Omni hygiene) AIwork4me will close #2875 with a redirect
   (report 04) so the long-lyrics fix has exactly one review surface: your
   fork's PR #2.

Everything above is reproducible from the evidence repository
`AIwork4me/YuE2-SGLang-ROCm`, branch `handoff/yue2-merge-readiness-20261026`
(reports 00–08, independent reviews, overlay patch, exact commands).
