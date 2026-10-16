# PHASE 0 — BASELINE VERIFICATION (READ-ONLY)

Date: 2026-10-16 (UTC)
Method: read-only inspection of local worktrees, git object database, live GitHub API (`gh`, account AIwork4me), and raw host artifacts. No file, branch, or PR was modified in Phase 0.

## 1. GPU ownership / active workloads

- GPU: single gfx1100 (AMD Radeon PRO W7900, 48 GiB VRAM reported as 51,522,830,336 B).
- `rocm-smi`: GPU use 0%, VRAM used 28,028,928 B (system residual only).
- All `sgl*` processes are `<defunct>` zombies from Oct 13–14 sessions; no live server, no active benchmark, no foreign workload.
- Verdict: **GPU idle; safe for later CPU-only/mocked testing; no GPU rerun required by this closure.**

## 2. Local repositories

| Repo | Path | Branch | HEAD | Status |
|---|---|---|---|---|
| sglang-omni (omni PR work) | `/workspace/yue2-omni-pr/repo` | `bench/omni-wsb` | `c4841f0c` | clean |
| sglang-omni (prompt-164 capfix worktree) | `/workspace/yue2-omni-pr/repo-ws164` | `bench/omni-wsb-capfix` | `c853135a` | clean |
| YuE2-SGLang-ROCm (evidence) | `/workspace/yue2-sglang-rocm-w7900/evidence-repo` | `handoff/omni-add_yue2-rocm-pr` | `a8a0fda2` | clean |

All three working trees: `git status --porcelain` empty (no uncommitted modifications).

Remotes:
- omni repos: `origin = yiakwy-xpu-ml-framework-team/sglang-omni` (partial clone, blob:none), `fork = AIwork4me/sglang-omni`.
- evidence repo: `origin = AIwork4me/YuE2-SGLang-ROCm`.
- Direct `git fetch` over HTTPS currently fails through the host CONNECT proxy (503); GitHub REST/GraphQL via `gh` works. Remote refresh for Phase 5 must use `gh api` or retry fetch later — recorded as an environment constraint, not a repo problem.

## 3. Commit ancestry vs expected anchors

| Expected | Found | Verdict |
|---|---|---|
| Omni ROCm patch HEAD `eca7770f…538` | Live PR #1 head = `eca7770fe196fe970f7d847858a5f92444b75538` (GitHub) | MATCH (remote) |
| Author base `85ae4b73…5a9` | Present; ancestor of all our omni branches | MATCH |
| Evidence commit `ccc3142…de08` | Parent of local evidence HEAD `a8a0fda2` (which adds only the raw-tree mirror commit on top) | MATCH |
| Local `fix/yue2-rocm-reference` | `91dccda1` — same comment-only content as `eca7770f`, local variant not pushed | CONSISTENT |

`eca7770f` subject = "review: drop AI notation, note ROCm flash-attn2 follow-up (comment-only)" — i.e. the pushed comment-update commit; the local `91dccda1` is the same change re-created locally. No divergence: `50c91c08` (the behavioral ROCm fix) is the common parent and is what run_config pins as `pr1_head`.

Full-run provenance pins (from `run_config.json` of run `omniwsb20261014T1323Z`):
`omni_commit=c4841f0c` (bench-only instrumentation), `pr1_head=50c91c08`, `author_base=85ae4b73` — consistent with the chain above.

## 4. Live PR / review state (via gh, not cache)

- **yiakwy/sglang-omni#1** (Omni ROCm PR): OPEN, MERGEABLE, base `add_yue2`, head `AIwork4me:fix/yue2-rocm-reference@eca7770f`. Reviews: 4 × COMMENTED by author (Oct 14), last = "LGM after updating the comments". **No new author review comments or requested changes since Oct 14.** Latest issue comment (Oct 16 11:25:58Z, id 6214464204) is ours (full WSB 384/384 results). No author integration of equivalent ROCm fixes detected on `add_yue2` (PR still MERGEABLE with no new commits).
- **sgl-project/sglang-omni#2540** (official Omni PR): OPEN, MERGEABLE, author yiakwy, head `add_yue2`, updated 2026-10-05. Not merged.
- **yiakwy/AMD-sglang-benchmark-fork#1** (original SGLang ROCm contribution): OPEN, MERGEABLE, head `def437fb`, updated 2026-10-14.
- Author H800 results: none posted on PR #1 (checked issue comments + reviews). H800 remains OUTSTANDING.

## 5. Raw benchmark artifact locations (host, immutable)

- Full run: `/workspace/yue2-omni-pr/bench/runs/omniwsb20261014T1323Z` (~29 GB incl. 384 WAVs)
  - Present: `run_config.json`, `generation_manifest.jsonl`, `evaluation_inputs.jsonl`, `generation_summary.json`, `scores/` (per_song.jsonl, summary.json, protocol.json, jobs, logs), `additional/` (MuLan/AMC), `run-state/` (main_pass_summary.json, prompt164_serving_disclosure.json), `audit.json`, songs/, server logs under `bench/logs/`.
- Pilot run: `/workspace/yue2-omni-pr/bench/runs/omni-pilot10x2` (20 candidates, 10 prompts).
- Serving raw request records: `/workspace/yue2-omni-pr/bench/benchmarks/bs1/raw_bs1_C1.jsonl` and `benchmarks/sweep/raw_sweep_C{1,2,4,8}.jsonl` — 24 records each, 120 total, fields `ok/status/finish_reason/wall_s/bytes/audio_s/rate/channels/item`.

### SHA256 anchor verification (full run, recomputed now)

| Artifact | Expected | Recomputed | Verdict |
|---|---|---|---|
| `run_config.json` | `8eeeb4c4…6176` | `8eeeb4c46f8aeefdf952875ede08c826c3590c660965422acd84131da7846176` | MATCH |
| `evaluation_inputs.jsonl` | `a906ab39…c100` | `a906ab391bf80992549fafd4b12631ec335963676d67fd790d30c39d588ac100` | MATCH |
| `generation_manifest.jsonl` | `92ef0148…71fb` | `92ef0148f948efddcdfc3b10e98c116af08b686c7c6b2273f5aacd0dff7471fb` | MATCH |

## 6. Evidence-chain state (issues to close in Phase 1)

Confirmed findings:

1. Published `evidence/omni_wsb/run_config.json` in the evidence repo has `run_id = omni-pilot10x2` — the PILOT config sits at the top of the FULL-run evidence directory. Same for `evidence/omni_wsb/generation_summary.json` (333 B, pilot 20-candidate summary) and `evidence/omni_wsb/audit.json` (mode "pilot", 20 candidates). **Ambiguity confirmed; correction required (Phase 1).**
2. Multi-session structure already documented on host: `run-state/main_pass_summary.json` records main pass = 382 complete / 2 failed (prompt-164 HTTP 400) / wall 83,989.3 s; resume pass (capfix worktree `c853135a`) = 2 complete / 828.2 s; the on-disk `generation_summary.json` of the full run was overwritten by the resume session — it must never be cited as a single-session 384-candidate generation record.
3. Prompt-164 root cause already receipted in `evidence/omni_wsb/prompt164_serving_disclosure.json`: generic `MAX_SPEECH_INPUT_CHARS=4096` (schema.py:77, speech_service.py:306) vs nested YuE2 input 4,194 chars; single-delta fix `Yue2PipelineConfig.max_speech_input_chars=None` exists locally as commit `c853135a` (moss_tts precedent config.py:105) — bench-only, NOT in PR #1.

## 7. Score integrity spot-check (no recomputation of model outputs)

From frozen `scores_summary.json` / `additional_summary.json` (full-run, hashes anchored):

- Candidate coverage: 384/384 scored, 192 prompts × 2; `full_192_standard_candidate_coverage = true`.
- Selected arm: exactly 192 selected candidates, 192 unique prompt indices; selection list carries per-candidate seed + audio SHA256.
- SongBench Global Avg: FULL 384 = **6.7301**; SELECTED 192 = **6.7323** (matches published "≈6.730 / ≈6.732").
- PER micro: FULL = 0.24819; SELECTED = 0.17608 (published 0.1761).
- MuLan (selected) = 0.50803; AMC (selected) = 0.40595.
- Truncated-but-valid: 5 (per prior strict audit; to be re-verified against per_song rows in Phase 1).

## 8. Serving metrics state (issues to close in Phase 2)

- `bench_serving_omni.py:172` computes `rtf_mean = mean(audio_s / wall_s)` — i.e. the real-time generation speed multiplier (audio/wall), NOT conventional RTF (wall/audio). Mislabel confirmed in code.
- `summary_bs1_C1.json` reports `gpu_util_mean_pct = 0` while `summary_sweep_C1.json` (same code, same host, later) reports 99.4 — parser verified functional on this host (`rocm-smi --showuse --csv` → `card0,<int>`); the bs1 zeros are therefore not a verified idle measurement. Will be marked `BS1_GPU_UTIL_NOT_VERIFIED` (Phase 2).
- VRAM/GTT reported in bytes; GB (10^9) vs GiB (2^30) labeling to be made explicit (Phase 2).
- RPS ≈ 0.0046 constant across C=1..8 with P50 scaling ~linearly — client-side concurrency only; no GPU batching claim to be made.

## 9. Baseline verdict

All expected SHAs, run identities, PR states, and raw artifacts verified against live sources. Two corrections are confirmed as genuinely required and are scoped to Phase 1 (pilot/full archive disambiguation) and Phase 2 (RTF labeling + GPU-util provenance). No evidence of author-side duplicate fixes; long-lyrics fix not yet upstream (Phase 3–5 needed).

**GATE: BASELINE_VERIFIED — subject to independent subagent confirmation below.**

## 10. Independent subagent confirmation

Independent read-only re-verification (explore subagent, 2026-10-16):

- Claims 1a, 1b, 2, 3, 4, 5, 6, 7: **CONFIRMED** (SHA256 anchors recomputed independently; rtf_mean mislabel pinned to `bench_serving_omni.py:172-173`; session split and score aggregates reproduced exactly).
- Claim 1c: CONFIRMED except "clean tree" — subagent observed untracked `reports/final_acceptance/` in the evidence repo. Resolution: that untracked directory is *this report itself*, created during Phase 0; the baseline state before Phase 0 had no modifications (tracked-file diff empty). Not a baseline discrepancy.

**FINAL: BASELINE_VERIFIED**
