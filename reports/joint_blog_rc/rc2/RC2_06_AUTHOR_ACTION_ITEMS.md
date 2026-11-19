# RC2_06b — Author collaboration action items

## Owner-side (before sending; no external action yet taken)

| ID | Action | Gate affected | Status |
|---|---|---|---|
| O-1 | Review + send `RC2_06_AUTHOR_MESSAGE_EN.md` (venue decision: WildSongBench issue vs email; avoid duplicate threads) | G9 | NOT_SENT |
| O-2 | Decide private transfer channel (HF private dataset / authors' secure upload) and authorize the ~15 GiB/arm transfer | EXT-1/EXT-5 | PENDING |
| O-3 | On Arm B completion: generate `armB_bundle_manifest.json` (same builder), attach fresh metrics to any follow-up | G3 | BLOCKED on campaign (running) |
| O-4 | Q3O scope decision: request author context or formally accept NOT_TESTED in publication scope | G6 | PENDING |

## Author-side asks (what a reply should contain)

| ID | Ask | Why it closes the gap |
|---|---|---|
| A-1 | Run the validated CUDA runbook on our transferred bundles (or host the scoring themselves) → return summary.json + per_song.jsonl + env record | A2/B2 cells: decisive H1-vs-H2 discrimination |
| A-2 | Provide official per-song PER receipts for the 8.44 % run (or authorize reference audio for C1) | prompt-level pairing; strongest closure |
| A-3 | State the evaluator commit + ASR serving config behind the Sept-12-2026 table | excludes H3 (version drift) |
| A-4 | Confirm/adjust the ±2 pp provisional PER parity criterion | publication acceptance criterion |
| A-5 | Confirm protocol semantics (4-pass min, lower-PER selection, capped retained) | locks the comparison protocol |
| A-6 | Optional: Q3O judge context | scope decision |
| A-7 | Review the eventual blog draft + claims matrix | G9 |

## Truth-tracking (what is NOT true yet — do not let drafts drift)

- Authors have NOT been contacted in this session; nothing sent.
- Author approval/endorsement: **NOT_PRESENT**.
- Fresh Arm B metrics: **NOT_PRESENT** (campaign running; ETA ≈ 2026-11-20T23Z).
- Cross-evaluator cells A2/B2/C1/C2: **BLOCKED_EXTERNAL** despite the ready kit.
