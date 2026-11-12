# 09 — License and Attribution Audit (Phase 9)

**Audit date:** 2026-11-11/12 · **Verifier:** publication-readiness mission · All statements verified against the live sources named below.

## 1. License inventory

| Component | Source of truth | License | Notes |
|---|---|---|---|
| This repository (code, scripts, tests, docs) | `LICENSE` | MIT (© 2026 AIwork4me) | code only; no weights/data |
| YuE inference code (`yue2`/`yue2-infer`) | YuE repo `LICENSE` | Apache 2.0 | |
| YuE2-3B / YuE2-Vae / YuE2-Vae-legacy **weights** | HF model cards + YuE `MODEL_LICENSE` | **CC BY-NC 4.0** | + individual-creator output-monetization grant (2026-09-16); companies need a separate commercial license |
| WildSongBench prompts/lyrics/reference data | HF dataset repo | **No license tag — treat as NOT redistributable** | lyrics/lyric-derived content must never enter this repo or the blog |
| wsb_metrics evaluator (code) | dataset bundle | bundled per-component licenses (`licenses/`) | |
| Qwen3-ASR-1.7B (PER evaluator weights) | HF | Apache 2.0 | |
| MuQ-MuLan-large | HF | CC BY-NC 4.0 | scoring-time use; not redistributed by us |
| MuQ-large-msd-iter / MERT (SongBench) | bundled `licenses/evaluation_models` | per-component (see bundle) | |
| allmusiccaps_te_trained_sigreg | HF | **CC BY-NC-SA 4.0** | share-alike applies to adaptations of the model, not our scores |
| SGLang (PR #42106 @ ced0ef7d) | repo | Apache 2.0 | unmerged PR — not official SGLang |
| SGLang-Omni (PR #2540) | repo | Apache 2.0 (verify at merge) | unmerged |
| ROCm PyTorch wheels | AMD | per AMD wheel license (pass-through use) | |

## 2. Rules this project must follow (release-blocking)

1. **No redistribution of model weights or benchmark content.** The repo
   carries hashes and download tooling only; `.gitignore` already blocks
   `*.safetensors`, `runs/`, `benchmark/`, `models/`.
2. **No WildSongBench lyrics, transcriptions, or benchmark audio in any
   publication artifact.** Evidence files store per-song receipts (IDs,
   hashes, counts, scores) — audited 2026-11-11: `evidence/per_song.jsonl`
   contains `reference_lyrics` fields inherited from the evaluator schema.
   **Finding F-1 (must fix before blog): strip or gate reference-lyric text
   from any NEW evidence published publicly; historical files are frozen but
   the blog must not quote them.** *(Status: OPEN — remediation decision
   needs owner input because rewriting historical evidence is forbidden; new
   mission evidence already avoids publishing lyrics.)*
3. **Demo audio in the blog/repo** must use (a) user-created original lyrics,
   or (b) lyrics licensed for the use, and must credit "Generated with YuE2
   (m-a-p), weights CC BY-NC 4.0" plus the runtime used. Do not use WSB
   prompts for demos.
4. **No commercial-use implication.** Weights are CC BY-NC 4.0; the
   individual-creator grant does not extend to companies. Blog wording must
   state this explicitly.
5. **Evaluator licenses pass through:** scoring uses MuQ-MuLan (CC BY-NC),
   AMT (CC BY-NC-SA), Qwen3-ASR (Apache 2.0), MERT (per bundle). Our
   published *scores* are facts about our outputs; we redistribute none of
   these models.
6. **Attribution requirements** for adapted code: our SGLang/evaluator
   patches are diffs against Apache-2.0/CC-licensed trees; upstream PRs must
   carry the same attribution this repo uses (`patches/README.md`,
   `upstream/PATCH_HANDOFF.md`).

## 3. Verification status

- HF license tags re-fetched live 2026-11-11 (all rows above).
- YuE `MODEL_LICENSE` read from the cloned repo @ `1116bea7`.
- wsb_metrics `licenses/` inventory listed; AGPL-3.0 component
  (`allmusiccaps` training data tooling) noted — it does not impose AGPL on
  our benchmark *results*; flag for author confirmation if the blog embeds
  evaluator code snippets.
- SGLang/sglang-omni license files present in the pinned checkouts.

## 4. Open licensing questions for the owner / authors

| # | Question | Blocking? |
|---|---|---|
| LQ-1 | May historical `evidence/per_song.jsonl` (contains `reference_lyrics`) stay public in this private-turn-public repo, or must we republish a lyric-redacted variant? | Blog publication: YES |
| LQ-2 | Confirm demo-audio attribution wording with YuE2 authors (joint blog). | Blog publication: YES |
| LQ-3 | AGPL component scope in the evaluator bundle for code snippets in the blog. | Snippets only: NO |
