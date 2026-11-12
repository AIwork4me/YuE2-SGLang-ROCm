# SGLang API (YuE2 on AMD ROCm)

What the SGLang integration actually exposes, verified on the W7900. The
YuE2 SGLang integration lives in **unmerged** upstream PRs
(sgl-project/sglang#42106 @ `ced0ef7d`, ported to sglang-omni as #2540).
It is **not** part of any official SGLang release; do not represent it as
such.

## Server

Launch (validated configuration — correctness-first ROCm flag matrix):

```bash
YUE2_WORKSPACE=$WS bash scripts/serve_yue2_gfx1100.sh     # 127.0.0.1:31000 ✅
```

Effective ROCm flags (all set by the launcher; patches enforce capability
gating for the same kernels):

| Flag | Value | Why |
|---|---|---|
| `SGLANG_YUE2_FAST_SAMPLER` | 0 | DeepSelect TopK is a CUDA-only JIT kernel |
| `SGLANG_YUE2_STEP_GRAPH` | 0 | fused decode+sample needs DeepSelect |
| `SGLANG_YUE2_FUSED_DECODE` | 0 | sgl_kernel absent on ROCm |
| `SGLANG_YUE2_FAST_NAR` | 0 | fused NAR needs sgl_kernel |
| `SGLANG_YUE2_FA3` | 0 | shared FA wrapper falls through to ATen native flash (validated) |
| `SGLANG_YUE2_BATCHED_AR` | 0 | BatchedGraphSampler needs DeepSelect |
| `SGLANG_YUE2_SESSION` | 1 | session GraphAR works (HIP graphs + ATen flash) |
| `SGLANG_YUE2_GRAPH_POOL` | 1 | graph memory pooling enabled |

## HTTP endpoints (original SGLang integration)

- `GET /health` — readiness ✅
- `POST /v1/audio/generations` — song generation ✅ (route from PR #42106)

Request fields (validated set):

```json
{
  "style": "[Tags]\nsoft pop\n",
  "lyrics": "[Lyrics]\n...\n",
  "seed": 831001,
  "cot": "full",
  "ode_steps": 32,
  "semantic_max_tokens": 9000,
  "output_path": "/abs/dir",
  "output_file_name": "song.wav",
  "artifacts_dir": "/abs/dir/candidate_id",
  "id": "candidate_id"
}
```

Response fields: `audio` (absolute wav path), `sample_rate` (48000), plus
artifact manifest references. The server writes the candidate bundle
(`abc_tokens.npy`, `plan.json`, `prefix.npy`, `semantic.npy`, `latent.npy`,
`audio.flac`, `config.json`) into `artifacts_dir`; official-schema
finalization (`score.abc`, `request.json`, `result.json`) is performed by
`scripts/finalize_candidate.py` (the campaign drivers invoke it). ✅

## Semantics you must not misreport

- **One generation at a time.** Concurrency from multiple clients queues;
  it does not parallelize on the GPU. Throughput claims must define this.
- **Determinism:** same seed + same server build + same flags ⇒ identical
  artifacts (validated historically; seed is applied to planning, semantic
  and NAR stages like the official protocol).
- **Long-lyrics behavior:** validated historically up to the official
  benchmark's full prompts; the former prompt-164 field-limit issue is
  re-verified each release (tracked in
  `docs/KNOWN_LIMITATIONS.md`). 🔬 pending current-tree regression.

## SGLang-Omni variant 🔬

sglang-omni PR #2540 exposes the OpenAI-style `/v1/audio/speech` route.
Historically validated end-to-end on this GPU class (384/384 campaign on
the validation branch). This mission treats original SGLang as the primary
public path (authors' PR) and Omni as the secondary; Omni regression is
scheduled with the current tree.
