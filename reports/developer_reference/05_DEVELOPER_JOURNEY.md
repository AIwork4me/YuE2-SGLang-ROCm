# 05_DEVELOPER_JOURNEY.md — RC6 A5: the developer golden path

The audience is a developer who has NEVER read RC1–RC5. Everything needed
for a first verified song is in `docs/QUICKSTART_W7900.md` +
`scripts/reference_cli.py`. Historical reports stay under
`reports/w7900_rc5/` (labelled Historical Reference) and are NOT on the
critical path.

## The journey

```
CLONE ──► PREFLIGHT ──► INSTALL ──► DOWNLOAD ──► GENERATE FIRST SONG
   │            │            │            │              │
   │            │            │            │              ▼
   │            │            │            │      VERIFY GPU & AUDIO ──► BENCHMARK PILOT
   │            │            │            │                                 │
   ▼            ▼            ▼            ▼                                 ▼
 (git clone) (doctor)   (pinned env) (SHA pins)                    (optional FULL benchmark)
                                                                            │
                                                                       COMPARE RESULTS
                                                                            │
                                                              TROUBLESHOOT / RESUME (docs/TROUBLESHOOTING.md)
```

Commands (one per step; all have `--help`; `--dry-run` shows the plan):

| Step | Command |
|---|---|
| Clone | `git clone https://github.com/AIwork4me/YuE2-SGLang-ROCm.git` |
| Preflight | `python3 scripts/reference_cli.py doctor` |
| Install | `python3 scripts/reference_cli.py install` |
| Download | `python3 scripts/reference_cli.py download` (part of install) |
| First song | `python3 scripts/reference_cli.py generate --lyrics examples/first_song/lyrics_en.txt --style examples/first_song/style.txt --seed 831001 --out-dir $WS/runs/my-first-song` |
| Verify | `python3 scripts/reference_cli.py verify --run-dir $WS/runs/my-first-song` |
| Pilot benchmark | `python3 scripts/reference_cli.py benchmark --mode pilot` |
| Full benchmark | `python3 scripts/reference_cli.py benchmark --mode full` (~24 h GPU) |
| Compare | `python3 scripts/reference_cli.py compare --run-dir <run>` |
| Status / Resume / Stop | `reference status` / `reference resume --run-dir <run>` / `reference stop` |
| Evidence package | `reference package-evidence --run-dir <run>` |

## Tiers (A5.5)

| Tier | FIRST_SONG | BENCHMARK_PILOT | FULL_WILDSONGBENCH |
|---|---|---|---|
| What | 1 complete song (original example lyrics) | 5 prompts × 2 = 10 candidates (official indices 0,1,2,79,81) | 192 × 2 = 384 candidates |
| Expected runtime | 5–10 min (incl. server boot) | ~1 h | ~24 h generation + ~28 h evaluation |
| Disk | ~1 GB | ~5 GB | ~50 GB (+ 18 GB backup volume) |
| GPU memory | 48 GiB class (W7900) | same | same |
| Host memory | 16 GiB free | same | 55 GiB cgroup headroom for Q3O |
| Network | one-time env+models (~25 GB, SHA-pinned) | none after install | none |
| Models | YuE2-3B + VAE (+ ASR/judges only when scoring) | + Qwen3-ASR for PER | + SongBench/MuLan/AMC/Q3O evaluator assets |
| License | YuE2 weights CC BY-NC 4.0 (check your use) | + WSB dataset terms | same |
| Expected output | song.wav + candidate bundle + verify receipt | journal + 10 candidates + pilot receipt | 384 candidates + five metrics + receipts |
| Verification | `reference verify` | `reference verify` (VALID_PILOT_ONLY) | `reference verify` + scoreboard |
| Failure recovery | rerun with a NEW --out-dir | `reference resume` | `reference resume` (checkpointed, crash-durable) |

Every tier writes a machine-readable JSON receipt; **pilot scores are never
compared with full-benchmark numbers** (the verification tool enforces
VALID_PILOT_ONLY).

## First-song acceptance (A5.4)

- **SMOKE_AUDIO_PASS**: a short audio clip renders, decodes, non-silent,
  correct rate/channels — quick pipeline sanity. NEVER presented as a song.
- **FULL_SONG_PASS**: a complete musical piece (all lyric sections), 48 kHz
  stereo, non-silent, GPU execution identity bound, official model identity
  in the candidate bundle, inference/audio timing recorded, server exits
  cleanly, no orphan processes, no residual GPU memory.
- The RC6 acceptance receipt is `05_FIRST_SONG_ACCEPTANCE.json` (generated
  from a real run on the W7900D).

## Verification verdicts (A5.6)

`scripts/rc6_verify_results.py` (also `reference verify`) emits:
`VERIFIED_REFERENCE_RUN` · `VERIFIED_WITH_DISCLOSED_DIFFERENCES` ·
`VALID_PILOT_ONLY` · `UNSUPPORTED_CONFIGURATION` · `INCOMPLETE` · `FAILED`.
Score proximity alone NEVER grants VERIFIED — identity chain, config, audio
integrity and coverage must all pass.

## Confusions eliminated (A5.2)

| Old confusion | Resolution |
|---|---|
| historical upstream `ced0ef7d` + patches 0001–0005 vs current `c67d541a` + import guards | QUICKSTART's canonical path is the RC5.1 frozen stack; the historical path is kept in a clearly-marked Historical section only |
| `git -C <upstream> apply patches/...` relative-path breakage | canonical commands resolve patch paths from the repo root (absolute), verified from a fresh clone |
| "vLLM unavailable on ROCm" | vLLM 0.19.1 ROCm runs (E2 PER arm) — what does NOT exist is vLLM **0.14.0** for ROCm (the official evaluator version) |
| "Q3O NOT RUN on 48 GB" (stale README/KNOWN_LIMITATIONS) | Q3O ran 192/192 on 48 GB with the ROCm-adapted judge (34 GPU + 14 CPU MoE layers) — official equivalence NOT_ESTABLISHED |
| 60 vs 120 selection-change numbers | both real: 60 changed prompts = 120 candidate-id symmetric difference; docs now use the four explicit fields |
| old perf/VRAM numbers | performance reference consolidated in `06_PERFORMANCE_REFERENCE.md` with units and measurement scope |
