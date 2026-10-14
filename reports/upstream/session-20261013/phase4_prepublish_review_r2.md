# Phase 4 Pre-Publish Review — Round 2 (post-fix re-review)

Reviewer scope: read-only re-review of `/tmp/opencode/pr1_body_draft.md` (PR body) and `/tmp/opencode/pr1_handoff_comment_draft.md` (handoff comment). All prior P1/P2 findings re-verified programmatically.

## Prior-findings verification

| # | Prior finding | Status | Evidence |
|---|---|---|---|
| P1 | curl `-d` JSON missing terminator / non-parsing nested JSON | **FIXED** | Payload extracted from the file replicating shell single-quote literal semantics; `json.loads` on the outer object succeeds (keys `model`, `voice`, `input`); `json.loads(outer["input"])` succeeds with exactly `{style, lyrics, cot, seed}`, `seed=831001` (number), `cot="full"`, lyrics `[verse]\nhello night\n[chorus]\nrun with me` with newline escapes intact. Raw payload ends `\"seed\":831001}"}` — inner JSON closes, then outer string quote, then outer `}`. Double-decode sanity check passed. |
| P1 | checkout+merge on author's active branch | **FIXED** | PR body §6: `git worktree add --detach /tmp/yue2-h800-check origin/add_yue2` + `git -C /tmp/yue2-h800-check merge --no-ff origin/fix/yue2-rocm-reference`. Comment step 1 mirrors this (`worktree add --detach`, "your active checkout and branches stay untouched"). Regex sweep: zero `git checkout`, zero `git push`, zero force flags in either doc. `worktree remove` cleanup documented. |
| P2 | comment missing explicit PR URL | **FIXED** | Comment line 3 cites `https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1`. |

## Clean-check regression sweep (no regressions)

- W7900 numbers exact in **both** docs and mutually consistent: 20.479 s / 47.239 s; SHA256 `358ffc66…d2882feed` and `218634d4…30526bd` (byte-identical strings across both docs).
- "natural EOS" wording intact: body §3 ("stopped at **natural EOS**. This is not a long-form endurance or stress claim."), comment line 9.
- python-multipart framed as platform-neutral in both: body §5 ("**platform-neutral packaging gap**, not a ROCm dependency"), comment line 29.
- No H800-run-by-us / cross-vendor bit-identical / parity claims: every occurrence is negated ("audio is **not** expected to be bit-identical across GPU vendors", "no performance/quality parity claim", "Identical audio SHA256 is **not** expected") or explicitly scoped to **simulated CUDA** A/B of base-vs-patched modules (previously accepted posture). NVIDIA run correctly stated as outstanding in both docs.
- No private links: URL inventory is `127.0.0.1:8000` (local curl), `sgl-project/sglang-omni#2540`, and the explicit PR #1 URL only.

## End-to-end consistency

- PR body: sections `## 1.`–`## 8.` all present in order; single fenced bash block, fences balanced; file ends with the complete §8 sentence (no truncation).
- Comment: 5-step checklist complete, ends "Thanks!" (no truncation).
- Cross-doc consistency: test counts (12/12, 37/37, 51-case), file list (stages/song/fastpath/fa3, +30/−6), seed/cot, and disclaimer posture agree between the two documents.

## Findings

- **P0:** none.
- **P1:** none.
- **P2:** none.
- **P3 (informational, non-blocking):** body §6 comment says "PASS looks like: … DeepSelect/fast-sampler/step-graph active per the same gates" — on a *detached-worktree merge of this PR* the gates are no-ops on CUDA, so "active" is the expected NVIDIA behavior; wording is correct but a reader conflating the ROCm bypass with the NVIDIA check could briefly misread it. No change required.

## PREPUBLISH_VERDICT

- `/tmp/opencode/pr1_body_draft.md`: **PASS**
- `/tmp/opencode/pr1_handoff_comment_draft.md`: **PASS**
