# LICENSE_AND_SECURITY_REVIEW.md — RC6 D5

## 1. Code license

Repository code: the repo's existing license file governs (LICENSE at the
root, unchanged by RC6). All RC6 additions (scripts, docs, tests) are
contributed under the same license.

## 2. Model / data / evaluator licenses

| Asset | License/terms | Our use | Redistribution |
|---|---|---|---|
| YuE2-3B + YuE2-Vae-legacy weights | CC BY-NC 4.0 (individual-creator monetization grant; companies need a license) | local inference, hash-pinned download from the official hub | **NO** — never committed/published |
| WildSongBench dataset (lyrics, reference text, audio) | dataset terms (@e361b85a) | local evaluation only | **NO** — never published; guarded |
| Frozen WSB evaluator bundle | bundle terms (THIRD_PARTY_NOTICES.md in the tree) | local, env-gated disclosed patches (math untouched) | **NO** |
| Qwen3-ASR / Qwen3-Omni judges | their hub licenses | local evaluation | **NO** |
| `examples/first_song/` lyrics + style | **original works created for this repository** (2026-11-27, RC6) | first-song acceptance | **YES** — free to use (unlike WSB content) |

## 3. Public evidence policy (enforced, not aspirational)

Published evidence = numeric receipts, hashes, source code, public-safe
synthetic fixtures, aggregate results, reproduction commands. Never: lyrics,
dataset text, ASR transcripts, audio, weights. Guards in CI:
`public_evidence_guard.py` + `evidence_lyrics_detector.py` + secret scan +
numeric-receipt integrity.

## 4. Historical Git objects (disclosed risk, unchanged)

The working-tree guards do NOT scan historical Git objects. main carries the
owner-authorized C1 redaction (PR #7, 2026-11-15); the mission chain carried
its own guards. RC6 policy:

- NO history rewriting, NO force-push (owner authorization would be
  required for any such plan, and none is requested).
- Any eventual merge of the mission chain into main must re-run the FULL
  guard suite on the merge result (recorded as a merge-time gate in the
  release gate ledger).
- A dedicated historical-object security review remains an open owner action
  (G24 note), inherited honestly from RC5.1.

## 5. Security review results (RC6)

- Secret scan at HEAD: PASS (no tokens/keys in the tree; gh tokens live only
  in the operator environment, never in files).
- Public evidence guard + lyrics detector at HEAD: PASS (regression suite).
- No un-authorized uploads: off-machine backup BLOCKED_EXTERNAL (owner has
  no destination); nothing was sent to third-party services.
- Generated audio from WSB inputs: stays local (restricted input ⇒ treat
  output as restricted); the first-song example (original lyrics) is the
  only publishable audio path.
- Tooling never requires root; no global ROCm driver mutation; no
  LD_LIBRARY_PATH tricks (venv-local userspace).
