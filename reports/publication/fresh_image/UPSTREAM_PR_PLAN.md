# UPSTREAM PR PLAN — Fresh Image (Phase P7 / P11)

Status: 2026-11-15 · All patches below are PREPARED; **no public upstream
submission before owner review/approval** (mission rule 15).

## Ownership analysis (confirmed)

| Issue | Owning repository | Evidence | Patch state |
|---|---|---|---|
| `torch-eager` rejected by standard-mode backend allowlist | **m-a-p/WildSongBench** (evaluator `wsb_eval.py::verify_inputs`) | generation with the officially documented ROCm backend cannot be scored; allowlist is `{'torch','vllm'}` | **0010 formalized** (this branch): `patches/0010-…patch` + README/RCA + bit-exact chain tests; one-line, no scoring-math change. Positive control: torch-eager accepted; negative: unknown backend still rejected |
| YuE2 native API `close()` does not release device memory in-process | multimodal-art-projection/YuE (yue2-infer) | PYTORCH_API_ACCEPTANCE item 13 (10.2→9.9 GiB after close+gc+empty_cache) | documented finding; upstream conversation piece (severity: low—fresh-process-per-song sidesteps); NO patch yet (needs upstream discussion of intended semantics) |
| `Sampling`/staged-API footguns (dict request rejected late; no seed in Sampling) | multimodal-art-projection/YuE | 3 corrections in PYTORCH_API_ACCEPTANCE | documentation-only contribution to upstream docs (proposed) |
| SGLang ROCm import/capability guards (aiter, DeepSelect, fa3 wrapper, kvcacheio) | sgl-project/sglang PR #42106 | patches 0001–0005, 0008 (historical, re-applied+verified on pristine ced0ef7d on this image) | maintained in AIwork4me until PR #42106 merge; upstreamable as PR comments |
| AR-stage server hang (~1/300 candidates) | sgl-project/sglang PR #42106 | historical RCA-10; NOT root-caused; watchdog restart is operational mitigation only | **investigation pending Arm B fresh campaign** (P5.2); no code fix claimed |
| HIP illegal-memory-access under evaluator+generator GPU sharing | PyTorch/ROCm layer (ownership NOT yet proven) | historical crash at prompts 164+; solo runs clean | P5.3 controlled reproduction queued (after campaigns; never during evidence production); needs minimal independent reproducer before any upstream assignment |
| Evaluator portability (0006/0007/0009) | m-a-p/WildSongBench | EVALUATOR_PATCH_AUDIT.md; chain-verified this image | keep as disclosed patches; author conversation prepared (they gate on WSB_ROCM_TORCH_OVERRIDE) |

## Submission packages (each must satisfy the 12-point evidence list)

1. **WildSongBench 0010** (ready): repo+base commit (dataset revision
   e361b85a), minimal repro (generate with official torch-eager backend →
   score → ValueError 'Unrecognized inference backend'), fix, tests
   (positive/negative), W7900 acceptance (Arm A campaign scoring will exercise
   it), NVIDIA-impact assessment (none — additive allowlist), scope/limits,
   PR text draft (in patch README).
2. **YuE2 upstream note** (draft after owner review): close() memory semantics
   + staged-API parameter gotchas; propose doc patch; include fresh-image
   acceptance receipts as supporting evidence.
3. **SGLang PR #42106 comments** (draft): re-verification of 0001–0005/0008 on
   a fresh W7900D image (bit-exact chain), plus Arm B fresh-campaign results
   when complete; AR-hang RCA findings if the fresh campaign reproduces it.

## Rule

Every item waits for: fresh-campaign acceptance evidence → owner review →
then public submission. Nothing is submitted from this session.
