# AUTHOR_REVIEW_REQUEST_DRAFT.md — RC6 B5 (draft, NOT sent)

Draft text for the owner to use when they choose the channel (GitHub issue
on the YuE2/WildSongBench repo, a PR comment on sgl-project/sglang#42106, or
email). Nothing has been sent without owner authorization; public-safe
content only (hashes/numbers/commands — never lyrics, audio, or ASR text).

---

Subject: YuE2 × WildSongBench full reproduction on AMD ROCm (W7900D) —
would you sanity-check our PER interpretation and two prepared CUDA
comparisons?

Hi — we completed a full WildSongBench reproduction of the YuE2 SGLang
integration (your PR #42106 head, commit `c67d541a`) on a single Radeon PRO
W7900D 48 GB (gfx1100, ROCm 7.14.1, torch 2.12):

- 384/384 candidates, 0 failures, official protocol untouched; 380/384
  byte-identical to our earlier run of the previous stack (4 diffs are
  FLAC-encoder-build-only: identical codec frames/duration/seed).
- SongBench 6.736891 (paper 6.7316), MuLan 0.509395 (0.5068),
  AllMusicCaps 0.405181 (0.4054), PER 17.77% under our frozen arm — and
  8.4488% vs the paper's 8.44% after we root-caused the gap to our ASR
  engine substitution (qwen_asr transformers backend repetition loop on
  hard candidates; same weights + same audio through vLLM decode normally;
  full 2×2 attribution on identical audio in our report).
- Q3O runs on the 48 GB card via a disclosed ROCm-adapted judge (official
  prompt/parser/weights verbatim, 34 GPU + 14 CPU MoE layers, deterministic
  tie-break, 192/192) — 4.394 vs paper 4.68; we claim NO official-engine
  equivalence (no CUDA host here; ~20% of routed slots sit on exact top-k
  ties).

Two things we would value your eyes on:

1. Does our PER interpretation match your understanding of the official
   evaluator? We have a hash-bound same-audio CUDA handoff package (384
   audio SHA256 + runbook + comparator, criteria pre-registered by you) if
   you can spare ~1 h of GPU time.
2. Is the official vLLM MoE kernel's top-k tie-break rule documented? It
   decides ~20% of routed slots and is the main Q3O comparability unknown.

Everything is public and verifiable:
https://github.com/AIwork4me/YuE2-SGLang-ROCm
(reports/developer_reference/author/AUTHOR_REVIEW_PACKAGE_EN.md is the
review entry point). No claim of your approval is made anywhere; we're
asking for exactly that review.

---

## Channel checklist before sending (owner)

- [ ] Choose channel: YuE2 repo issue / PR #42106 comment / email
- [ ] Confirm the target repo's policy on benchmark-derived numbers
- [ ] Public-safety scan of the exact text (lyrics/audio/ASR-text free)
- [ ] Record submission in AUTHOR_ACCEPTANCE_MATRIX.json (SUBMITTED + channel + timestamp)
