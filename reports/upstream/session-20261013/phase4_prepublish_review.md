# Phase 4 — Pre-Publish Review (PR body + handoff comment)

Reviewer: independent, read-only. Evidence base: today's verified audit (W7900 gfx1100 E2E, patch 50c91c0 stats, GPU-trace scope, python-multipart finding, private-repo constraint).

## Findings

### PR body (/tmp/opencode/pr1_body_draft.md)

1. **P1 — §6 curl JSON is malformed (truncation).** The request body ends `…\"seed\":831001}'` — after the inner JSON's closing `}`, the outer `"input"` string is never closed and the outer JSON object is never closed. Valid form: `…\"seed\":831001}"}` (inner `}`, close `"`, outer `}`). As written, a maintainer copy-pasting this gets an instant 400/parse error. The escaping pattern itself is correct: `\"` for quotes at the outer layer, and `\\n` correctly decodes to `\n` at the inner layer → real newlines after the second JSON parse. Only the terminator is missing.

2. **P1 — §6 merge sequence contradicts its own "isolated worktree" framing.** `git checkout add_yue2 && git merge --no-ff fix/yue2-rocm-reference` switches the author's existing checkout and creates a merge commit directly on their local `add_yue2` — exactly the "author-branch damage" the section promises to avoid. Safer: `git fetch origin add_yue2 && git worktree add --detach /tmp/yue2-h800 add_yue2` then merge inside the worktree (detached HEAD → author branches untouched). Positive: no force-push, no history rewrite anywhere.

3. **P3 — Specifics beyond the audited evidence** (consistent, but confirm before publish): log quote `samples=2267456` (2267456/48000 = 47.2387 s ≈ 47.239 s ✓), rocm-smi VRAM 21→35%, model/VAE commits `1a96eca`/`b54118f0` + 628/628 tensors, HIP 7.14.60850, and "11/12 fail on unpatched base".

4. **P3 — Grammar:** §5 "This is **platform-neutral packaging gap**" → "a platform-neutral packaging gap".

5. **P3 — Line 1 ambiguity:** "on top of this branch's `add_yue2`" reads oddly; prefer "on top of `add_yue2` @ 85ae4b7". The base SHA 85ae4b7 is never stated anywhere — adding it aids reproducibility.

6. **P3 — Curl observability:** no `-w '%{http_code}'` or `--fail`, yet the PASS criterion is "HTTP 200". One flag addition makes the check self-verifying.

### Handoff comment (/tmp/opencode/pr1_handoff_comment_draft.md)

7. **P2 — No explicit PR URL/number reference.** Only "this small PR" (works when posted on the PR itself, but the required unambiguous reference — e.g. "PR #NNNN: <URL>" — is absent; #2540 is the issue, not this PR).

8. **P3 — Self-contradictory phrasing:** "no changes to your active branch needed beyond a test merge" — a test merge IS a change. Recommend detached-worktree wording (see finding 2).

9. **P3 —** "exact curl in the PR body" inherits the PR body's curl bug (finding 1) until fixed.

## Checklist results

| # | Check | PR body | Comment |
|---|---|---|---|
| 1 | First paragraph = W7900 ROCm real HTTP pass + CUDA fast paths preserved | PASS | — |
| 2 | All 8 required sections present, correct order | PASS | — |
| 3 | W7900 numbers exact (20.479 s / RMS 0.0860 / `358ffc66…feed`; 47.239 s / RMS 0.1470 / `218634d4…26bd`; 48 kHz stereo; seed 831001; 15.25 s smoke inferential) | PASS | PASS |
| 4 | Natural EOS wording; no long-song/stress claim | PASS | PASS |
| 5 | python-multipart = platform-neutral, not ROCm-specific (v0.0.32) | PASS | PASS |
| 6 | No H800-by-us / bit-identical / quality-parity / production-readiness / WSB-closure / performance claims; author's base-PR NVIDIA eval correctly attributed, not appropriated | PASS | PASS |
| 7 | No private-repo (AIwork4me/YuE2-SGLang-ROCm) links; only public sgl-project refs | PASS | PASS |
| 8 | GPU trace = full-config window only; smoke inferential via 15.25 s synth elapsed | PASS | — |
| 9 | H800 instructions isolated + safe; no force-push/rewrite; SHA-match explicitly not required | **FAIL (finding 2)**; no-SED requirement PASS | PASS |
| 10 | Comment required elements (PR URL ref, W7900, 4 files, 12/12, 37/37, 51-case, unchanged-by-construction, H800 outstanding, integration ask, single venue → no duplicate posting) | — | **P2 gap (finding 7)**; all others PASS |
| 11 | Tone collaborative, concise, no pressure/partnership announcement | PASS | PASS |

## Verdicts

- **pr1_body_draft.md: PREPUBLISH_VERDICT: FAIL** — fix finding 1 (broken curl JSON) and finding 2 (merge command mutates author branch) before publishing; findings 3–6 optional polish.
- **pr1_handoff_comment_draft.md: PREPUBLISH_VERDICT: PASS** — with finding 7 (add explicit PR link, one line) and finding 9 (verify after PR-body curl fix) addressed.
