# 07 — Upstream patch matrix (live state 2026-11-19)

Live GitHub check executed 2026-11-19T02:05Z via `gh pr view`.

| Target | PR/patch | State (live) | Content | Our evidence | Next action (owner-gated) |
|---|---|---|---|---|---|
| sgl-project/sglang | [#42106 "Add yue2"](https://github.com/sgl-project/sglang/pull/42106) | **OPEN** (updated 2026-11-02) | YuE2 support in mainline SGLang | patches 0001–0005, 0008 re-applied + verified on pristine `ced0ef7d` on this image; fresh Arm B campaign (in flight) is the hardware validation | post-campaign: attach W7900D validation receipts + ROCm guard deltas as PR comments; do NOT submit new patches without owner approval |
| sgl-project/sglang-omni | [#2540 "Add yue2 (port)"](https://github.com/sgl-project/sglang-omni/pull/2540) | **OPEN** (updated 2026-11-06) | Omni port of the YuE2 support | historical omni campaign (384/384 FULL, PER 17.61%) | same as above |
| yiakwy-xpu-ml-framework-team/sglang-omni | [#1 "enable ROCm reference path"](https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1) | **OPEN** (updated 2026-10-16) | ROCm reference path without CUDA regression | our 0001–0005 chain supersedes/overlaps; validation on W7900D complete (acceptance PASS 2026-11-19 incl. real music generation) | reconciliation comment w/ fresh receipts after campaign |
| yiakwy-xpu-ml-framework-team/sglang-omni | [#2 "allow full-song lyrics"](https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/2) | **OPEN** (updated 2026-10-16) | full-song lyrics in speech requests | exercised by every WSB full-song request (384× multiple campaigns) | same |
| m-a-p/WildSongBench | patch **0010** (torch-eager allowlist) | **PREPARED, NOT SUBMITTED** | one-line allowlist fix; scoring math unchanged | `patches/0010-…patch` + README + bit-exact chain tests; fresh Arm A full campaign ran under torch-eager | submit after owner approval; needs upstream repo issue first |
| m-a-p/WildSongBench | patches **0006/0007/0009** (evaluator ROCm) | **DISCLOSED, NOT SUBMITTED** | Qwen3-ASR via transformers on ROCm; per-ROCM lock; reuse | chain-verified; all fresh scorings used them, disclosed in every report | author conversation (see 07_AUTHOR_REVIEW_REQUEST) |
| multimodal-art-projection/YuE | `close()` memory finding | **DOCUMENTED, NO PATCH** | ~10.2 GiB device mem before close, ~0.34 GiB released (in-process) | PYTORCH_API_ACCEPTANCE item 13; M4.3 re-validation queued on GPU window | upstream discussion; propose semantics (release pipeline buffers on close) |
| multimodal-art-projection/YuE | staged-API footguns (3) | **DOCUMENTED** | dict request rejected late; Sampling seed; etc. | PYTORCH_API_ACCEPTANCE | docs PR proposal (owner-gated) |
| sgl-project/sglang | AR-stage hang (~1/300) | **OPEN RCA** | not root-caused; watchdog is operational mitigation only | historical RCA-10; M4.1 investigation scheduled post-campaign (needs dedicated GPU window) | no claim until root-caused |
| ROCm/PyTorch layer | HIP illegal memory access (GPU sharing) | **OPEN RCA** | solo operation safe; concurrent eval+gen historically crashed | M4.2 controlled reproducer scheduled post-campaign in isolated window | minimal reproducer before any upstream assignment |

Rules honored: nothing submitted upstream from this session; every package
below is prepared for owner review only.
