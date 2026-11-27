# PUBLIC_CLAIMS_MATRIX.md — RC6: exactly what may be said publicly

Every public claim maps to evidence; anything not in the "may claim"
column must not be said. False-approval claims are a negative-control
target of the regression suite.

| Topic | MAY claim (with evidence) | MUST NOT claim |
|---|---|---|
| Generation | "384/384 WildSongBench candidates generated on W7900D (gfx1100, ROCm 7.14.1, torch 2.12.0+rocm7.14.1) with the pinned SGLang PR #42106 snapshot c67d541a + import-guard patches; 0 failures; 380/384 byte-identical to the prior-stack run (4 differences are FLAC-encoder-build-only, PCM-level parity unprovable, honestly recorded)" | "bit-identical 384/384"; "official SGLang release supports this" (PR unmerged) |
| SongBench / MuLan / AMC | "official evaluator verbatim on the frozen selected-192: 6.736891 / 0.509395 / 0.405181 (paper: 6.7316 / 0.5068 / 0.4054)" | mixing corrected-selection numbers into the frozen scoreboard |
| PER | "frozen arm 17.7699% under the disclosed transformers ASR substitution; corrected vLLM 0.19.1 arm 8.4488% vs paper 8.44% (Δ 0.009 pp, zero tuning), reported as a SEPARATE arm; 2×2 attribution computed on identical audio" | "we reproduce the official PER" (official CUDA engine never ran here); any averaging of arms |
| Q3O | "192/192 valid under the ROCm-adapted judge (official prompt/parser/weights verbatim; 34 GPU + 14 CPU MoE layers; deterministic tie-break; 5-run token-identical); 4.393986/5; official equivalence NOT_ESTABLISHED" | "Q3O equivalent to the official judge"; "20% of tokens wrong" (tie-rate is a routing-slot statistic) |
| Determinism | "380/384 file-byte-identical; 4 candidates: duration/frames/seed identical, container bytes differ; encoder-build sensitivity demonstrated; historical PCM identity UNVERIFIABLE (artifacts absent)" | "the 4 files are proven identical" |
| Performance | "P50 275.27 s / mean 284.78 s per candidate, sequential single-GPU; RTF mean 1.2866; Q3O peak VRAM 42.41 GiB" | throughput/concurrency claims; mixing GB/GiB |
| Hardware | "PHYSICAL_PASS on W7900/W7900D 48 GiB" | "all RDNA3 cards supported"; any EXPECTED_BUT_UNVERIFIED as PASS |
| Author | "author review package READY (A01–A12); not submitted; no author approval exists" | "author-verified/author-approved" ANYWHERE |
| AMD | "AMD engineering acceptance package READY (AMD01–AMD10); not submitted; no AMD approval exists" | any AMD approval/publication claim |
| Third-party | "fresh-clone same-host reproduction (Mode 2) + independent-runner task package" | "independently reproduced by a third party" (no third party has run it) |
| Release | "Developer Reproduction Reference v1.0-rc1 prepared; CI green at exact HEAD" | "released/published" (no GitHub Release/tag without owner authorization) |
| Upstream | "pinned PR snapshot; 0004/0005 absorbed; scheduler busy-spin open upstream" | "SGLang stable supports YuE2 on ROCm" |

## Wording fixes shipped in RC6

- RC5.1 handoff "author-verified commands" → "commands executed on our
  W7900 rig" (author/AUTHOR_REVIEW_PACKAGE_EN.md §6).
- "Q3O NOT RUN / NOT TESTED on 48 GB" (stale README/KNOWN_LIMITATIONS) →
  the ROCm-adapted status with caveats.
- "60 changed prompts" vs "selection_change_count=120" → the four explicit
  fields (changed prompts 60, removed 60, added 60, symmetric difference
  120).
