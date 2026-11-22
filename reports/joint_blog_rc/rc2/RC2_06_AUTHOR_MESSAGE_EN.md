# RC2_06 — Sendable message to the YuE2 authors (English, final draft)

**Status: PREPARED — NOT SENT. External posting requires explicit owner
authorization (gate G9 depends on a real reply, never on this draft).**

Suggested venue: a single new issue on `m-a-p/WildSongBench` (or the YuE2
repo) titled "Reproducing the standard WildSongBench comparison on AMD ROCm
— PER gap investigation + cross-evaluator request", unless an existing
thread is preferred by the owner. Email is equally usable verbatim.

---

Subject: YuE2 on AMD ROCm — benchmark reproduction matches on 3 of 4
metrics; help us close a PER gap (cross-evaluator request)

Dear YuE2 team,

We have completed a fully-receipted reproduction of the standard YuE2
WildSongBench protocol (192 prompts × 2 candidates, official seeds, frozen
protocol lock) on an AMD Radeon Pro W7900D (gfx1100, ROCm), using both your
native PyTorch implementation and an SGLang serving path. Headline numbers
on the frozen evaluator (with our disclosed ROCm ASR backend patches):

| Metric (selected-192) | Official reference | Native torch on W7900D | SGLang on W7900D (fresh, in progress) |
|---|---:|---:|---:|
| SongBench GA | 6.7316 | 6.7044 | (campaign running; prior image: 6.7376) |
| MuLan | 0.5068 | 0.4970 | (prior image: 0.5093) |
| AllMusicCaps | 0.4054 | 0.4010 | (prior image: 0.4056) |
| PER | 8.44 % | **16.83 %** [14.9–18.9] | (prior image: 17.77 %) |

Three of four metrics reproduce your reference within ±0.03 / ±0.01 / ±0.01.
PER does not — and the gap is common-mode: your own implementation shows the
same offset on our hardware as SGLang (uncapped-only PER: 16.15 % vs
16.14 % across arms and GPU families), all four ASR passes are
byte-identical on 384/384 candidates, our independent recomputation of your
selection rule reproduces your aggregation exactly, and the transcript
errors are deletion-dominant (hypotheses systematically shorter than the
references). This pattern points at our ROCm ASR evaluation backend as the
prime suspect — but we cannot prove it without a same-audio
cross-evaluator comparison, and we commit in advance to either conclusion.

**Our asks (each has a prepared, tested kit):**

1. **Score our audio with your CUDA evaluator** (closes the question
   decisively). May we privately transfer the complete per-candidate
   verification bundles (16.3 GiB per arm: result/request/config/FLAC +
   artifacts, SHA256-manifested and end-to-end verified; performances of
   licensed WSB lyrics, private channel only — never public)? Exact 6-command
   runbook (validated against the official frozen checker on our side):
   `rc2/RC2_03_AUTHOR_CUDA_HANDOFF/README_CUDA_RUNBOOK.md`. Alternatively,
   run it in your environment and return `summary.json` + `per_song.jsonl`.
   Pre-registered reading: ≈8–11 % ⇒ our ROCm ASR backend is the cause;
   ≈16–18 % ⇒ generation-side; we publish whichever result occurs.
2. **Reference per-song receipts** for the 8.44 % run (means alone cannot
   localize disagreement), or authorization to score your reference audio
   on our evaluator.
3. **Evaluator identity**: the exact WildSongBench commit and ASR serving
   configuration behind the September-12-2026 comparison table, to exclude
   version drift.
4. **Tolerance**: our pre-registered parity criterion is |PER − official|
   ≤ 2 pp. Is that the right bar for a joint technical article?
5. **Protocol confirmations**: four ASR passes with min selection;
   lower-PER candidate selection for all metrics; capped outputs retained —
   all implemented; please flag any deviation you see.
6. **Q3O scope**: our 48 GB card appears below the official judge's memory
   requirement; we will keep Q3O NOT_TESTED rather than substitute a judge,
   unless you can share the judge context (optional item 7 in our internal
   list; happy to drop it if out of scope).
7. **Blog claims review**: before any publication, we will send the draft
   and a claims matrix (every number → evidence path) for your review.
   Nothing will imply your endorsement until you say so.

Everything is reproducible from the public repository
`AIwork4me/YuE2-SGLang-ROCm` (pinned model/VAE/dataset identities, frozen
protocol lock, per-candidate provenance chains; licensed-material evidence
redacted, raw receipts available privately on request).

We are glad to adapt the format to whatever is easiest for you (issue, email,
or a short call). Thank you for the excellent benchmark design — it is the
reason this gap is measurable at all.

Respectfully,
— AIwork4me / YuE2-SGLang-ROCm team

---

## Accuracy checklist (owner pre-send verification)

- [x] Arm B fresh campaign described as IN PROGRESS (no future metric implied)
- [x] Prior-image Arm B numbers explicitly labeled as a separate generation
- [x] Transfer size corrected to ~15 GiB/arm (RC2 kit audit; old drafts said ~2 GiB)
- [x] No endorsement implied; no claim that authors responded
- [x] Every number matches receipts (6.7044/0.4970/0.4010/16.83 % Arm A fresh;
      6.7376/0.5093/0.4056/17.77 % Arm B prior image; official 6.7316/0.5068/0.4054/8.44 %)
- [x] Runbook validated (official prepare_inputs PASS 384/384 on our side)
- [ ] Owner: choose venue (issue vs email) — no duplicate threads
- [ ] Owner: authorize private transfer channel decision (EXT-5)
