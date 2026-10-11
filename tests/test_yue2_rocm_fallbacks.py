"""ROCm fallback correctness tests for YuE2/SGLang (gfx1151 + gfx1100).

Run:  source environments/<env>/bin/activate && YUE2_WORKSPACE=<ws> python -m pytest tests/test_yue2_rocm_fallbacks.py -v
(requires models/YuE2-3B and models/YuE2-Vae-legacy downloaded; ~7 GB GPU use)

Covers, in order:
1. aiter import guards (patches 0001-0003) make the quantization chain importable
2. DeepSelect fast sampler is unavailable and the reference sampler takes over
3. torch.ops.aten._flash_attention_forward (private ATen op reached via
   SGLANG_YUE2_FA3=0) is numerically correct on this gfx target for the exact
   varlen/GQA/seqused_k pattern GraphAR uses
4. masked SDPA (GraphAR's non-flash fallback) falls back to MATH and is correct
5. HIP (CUDA) graph capture+replay works
6. real-model AR: GraphAR(flash) logits vs eager HF forward logits
7. reference NAR solver produces finite latents (small budget)
8. VAE tiled decode produces finite audio (small budget)
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pytest
import torch

WS = os.environ.get("YUE2_WORKSPACE",
                   str(Path(__file__).resolve().parents[2]))
MODEL_DIR = f"{WS}/models/YuE2-3B"
VAE_DIR = f"{WS}/models/YuE2-Vae-legacy"

os.environ.setdefault("SGLANG_YUE2_VAE_DIR", VAE_DIR)


def test_kvcacheio_import_guards():
    """Patches (kvcacheio guards): host-KV modules import without sgl_kernel."""
    import importlib
    assert importlib.util.find_spec("sgl_kernel") is None, "precondition: sgl_kernel absent"
    for mod in ("sglang.srt.mem_cache.hisparse_memory_pool",
                "sglang.srt.mem_cache.memory_pool_host",
                "sglang.srt.mem_cache.pool_host.mha"):
        importlib.import_module(mod)


def test_quantization_chain_imports():
    """Patches 0001-0003: the aiter-gated quantization modules import on aiter-less ROCm."""
    from sglang.srt.layers import quantization as qz  # noqa: F401
    from sglang.srt.layers.quantization.quark.schemes.quark_w4a4_mxfp4 import (  # noqa: F401
        QuarkW4A4MXFP4,
    )
    from sglang.srt.layers.quantization.quark.schemes.quark_w4a4_mxfp4_moe import (  # noqa: F401
        dynamic_mxfp4_quant,
    )
    assert dynamic_mxfp4_quant is None, "without aiter the scheme must import to None"


def test_deepselect_fallback():
    """DeepSelect wrapper imports on ROCm but the kernel is unsupported -> reference sampler."""
    from sglang.srt.models.yue2 import fastpath
    from sglang.kernels.ops.deep_select import is_deepselect_supported

    # The in-tree wrapper is importable everywhere (pure Python)...
    assert fastpath._load_topk_backend() is not None
    # ...but the CUDA JIT kernel cannot run on this ROCm target
    # (torch.version.cuda None on ROCm; gfx capability outside SM 9/10 either way).
    assert is_deepselect_supported() is False
    # Therefore the fast sampler must not be selected (patch 0004)...
    assert fastpath.fast_sampler_available() is False


def _manual_varlen_attn(q, k, v, hq, hkv, scale):
    L = k.shape[0]
    kf, vf = k.transpose(0, 1), v.transpose(0, 1)
    if hq != hkv:
        kf = kf.repeat_interleave(hq // hkv, 0)
        vf = vf.repeat_interleave(hq // hkv, 0)
    scores = torch.einsum("hd,hld->hl", q * scale, kf.float())
    probs = scores.softmax(-1)
    return torch.einsum("hl,hld->hd", probs, vf.float())


def test_aten_flash_varlen_numerics():
    """The private ATen flash op (SGLANG_YUE2_FA3=0 path) honors varlen+GQA+seqused_k on this ROCm target."""
    from sglang.srt.models.yue2 import fa3

    torch.manual_seed(0)
    HQ, HKV, HD = 8, 2, 64
    scale = 1.0 / math.sqrt(HD)
    q = torch.randn(2, HQ, HD, device="cuda", dtype=torch.bfloat16)
    k = torch.randn(32, HKV, HD, device="cuda", dtype=torch.bfloat16)
    v = torch.randn_like(k)
    cu_q = torch.tensor([0, 1, 2], dtype=torch.int32, device="cuda")
    cu_k = torch.tensor([0, 16, 32], dtype=torch.int32, device="cuda")
    seqused = torch.tensor([5, 16], dtype=torch.int32, device="cuda")
    out = fa3.varlen_attention(q, k, v, cu_q, cu_k, 1, 16, seqused_k=seqused)
    torch.cuda.synchronize()
    assert out.shape == (2, HQ, HD)
    maxdiff = 0.0
    for row, used in ((0, 5), (1, 16)):
        ref = _manual_varlen_attn(q[row].float(), k[row * 16:row * 16 + used].float(),
                                  v[row * 16:row * 16 + used].float(), HQ, HKV, scale)
        maxdiff = max(maxdiff, (out[row].float() - ref).abs().max().item())
    assert torch.isfinite(out).all()
    assert maxdiff < 0.02, f"flash varlen numerics off: {maxdiff}"


def test_masked_sdpa_math_fallback():
    """GraphAR's non-flash attention (bool mask + GQA) must be correct via MATH on ROCm."""
    torch.manual_seed(1)
    B, HQ, HKV, HD, L = 1, 8, 2, 64, 12
    q = torch.randn(B, HQ, 1, HD, device="cuda", dtype=torch.bfloat16)
    k = torch.randn(B, HKV, L, HD, device="cuda", dtype=torch.bfloat16)
    v = torch.randn_like(k)
    visible = torch.ones(B, 1, 1, L, dtype=torch.bool, device="cuda")
    visible[..., 7:] = False  # hide tail slots (bool mask: True = allowed)
    out = torch.nn.functional.scaled_dot_product_attention(
        q, k, v, attn_mask=visible, is_causal=False, enable_gqa=HQ != HKV)
    kf = k[0].repeat_interleave(HQ // HKV, 0).float()
    vf = v[0].repeat_interleave(HQ // HKV, 0).float()
    scores = torch.einsum("hd,hld->hl", q[0, :, 0].float() / math.sqrt(HD), kf[..., :7, :])
    probs = scores.softmax(-1)
    ref = torch.einsum("hl,hld->hd", probs, vf[..., :7, :])
    diff = (out[0, :, 0].float() - ref).abs().max().item()
    assert diff < 0.02, f"masked SDPA numerics off: {diff}"


def test_hip_graph_capture_replay():
    g = torch.cuda.CUDAGraph()
    a = torch.ones(8, device="cuda")
    s = torch.cuda.Stream()
    s.wait_stream(torch.cuda.current_stream())
    with torch.cuda.stream(s):
        _ = a * 2
    torch.cuda.current_stream().wait_stream(s)
    with torch.cuda.graph(g):
        a.mul_(2.0)
    a.fill_(1.0)
    g.replay()
    g.replay()
    torch.cuda.synchronize()
    assert torch.allclose(a, torch.full_like(a, 4.0)), a


@pytest.fixture(scope="module")
def runtime():
    rt = type("R", (), {})
    from sglang.srt.model_loader.yue2_loader import Yue2Runtime

    rt.obj = Yue2Runtime.from_paths(MODEL_DIR, VAE_DIR, torch.device("cuda"))
    yield rt.obj
    del rt.obj
    torch.cuda.empty_cache()


def test_model_loads_on_gpu(runtime):
    model = runtime.model
    assert next(model.parameters()).device.type == "cuda"
    assert next(model.parameters()).dtype == torch.bfloat16
    assert runtime.vae is not None
    assert runtime.tokenizer is not None


def test_ar_graph_vs_eager_logits(runtime):
    """GraphAR(auto->flash on ROCm) must match the eager HF forward on real weights."""
    from sglang.srt.models.yue2.cuda_graph import GraphAR
    from sglang.srt.models.yue2.protocol import EOD

    torch.manual_seed(7)
    model = runtime.model
    tokenizer = runtime.tokenizer
    text = "Generate a chord-annotated ABC transcription, then generate music with codec tokens from the given conditions.\n[Tags]\nsoft pop\n[Lyrics]\nA short ROCm test phrase.\n"
    prefix = [EOD] + tokenizer.encode(text) + [151847]  # + ABC_START
    max_tokens = 8

    graph = GraphAR(model, [prefix], max_tokens)  # attention_backend auto
    backend = graph.attention_backend
    logits_g = graph.prefill()
    token = int(logits_g[0].argmax())
    out_g = graph.step(token)
    graph.close()

    from sglang.srt.models.yue2.modeling_yue2 import StaticKVCache

    cfg = model.config
    cache = StaticKVCache(num_layers=cfg.num_hidden_layers, batch_size=1,
                          num_kv_heads=cfg.num_key_value_heads,
                          max_seq_len=len(prefix) + max_tokens,
                          head_dim=cfg.head_dim, dtype=torch.bfloat16, device="cuda")
    with torch.inference_mode():
        out_e = model(torch.tensor([prefix], device="cuda"), past_key_values=cache,
                      use_cache=True, logits_to_keep=1).logits[:, -1]
        out_e2 = model(torch.tensor([[token]], device="cuda"), past_key_values=cache,
                       use_cache=True, logits_to_keep=1).logits[:, -1]
    prefill_diff = (logits_g[0].float() - out_e.float()).abs().max().item()
    step_diff = (out_g[0].float() - out_e2.float()).abs().max().item()
    scale = out_e.float().abs().max().item()
    assert torch.isfinite(logits_g).all() and torch.isfinite(out_g).all()
    assert prefill_diff < 0.05 * max(scale, 1.0), (prefill_diff, scale)
    assert step_diff < 0.05 * max(scale, 1.0), (step_diff, scale)
    print(f"\n[ar-vs-eager] backend={backend} prefill_max|diff|={prefill_diff:.4f} "
          f"step_max|diff|={step_diff:.4f} logit_scale={scale:.2f}")


def test_reference_sampler_distribution_matches_fastpath_semantics():
    """distribution() (reference path) masks by absolute token id at real vocab width."""
    from sglang.srt.models.yue2.protocol import (ABC_END, EOD, MUSIC_END,
                                                 Sampling)
    from sglang.srt.models.yue2.sampling import distribution

    torch.manual_seed(3)
    vocab = 184704
    logits = torch.randn(1, vocab, device="cuda", dtype=torch.bfloat16).float()
    logits[0, MUSIC_END] = 5.0   # force the end token into top-k deterministically
    logits[0, ABC_END] = 5.0
    sampling = Sampling(temperature=1.0, top_p=0.95, top_k=50, repetition_penalty=1.2,
                        penalty_window=50, min_tokens=0, max_tokens=9000)

    # semantic phase: only MUSIC_END and the codec region are reachable
    scores = distribution(logits.clone(), sampling, [3, 3, 7], step=0, phase="semantic")
    allowed = scores[0] > float("-inf")
    assert scores[0, :MUSIC_END].isinf().all()          # everything before MUSIC_END masked
    assert scores[0, MUSIC_END].isfinite()              # end token reachable
    codec_allowed = allowed[MUSIC_END + 1:]
    assert int(codec_allowed.sum()) > 0
    assert int(allowed.sum()) <= 50                     # top-k applied

    # abc phase: ordinary text vocabulary plus ABC_END, min_tokens blocks the end
    abc_sampling = Sampling(temperature=0.7, top_p=0.9, top_k=30, repetition_penalty=1.005,
                            penalty_window=100, min_tokens=32, max_tokens=4096)
    scores = distribution(logits.clone(), abc_sampling, [5], step=0, phase="abc")
    assert scores[0, :EOD].isfinite().any()
    assert scores[0, ABC_END].isinf()                   # blocked while step < min_tokens
    assert scores[0, EOD:].isinf().all()                # codec region masked in abc phase


def test_nar_solver_finite(runtime):
    from sglang.srt.models.yue2.nar import synthesize

    model = runtime.model
    prefix = [151643] + runtime.tokenizer.encode("[Tags]\nsoft pop\n[Lyrics]\nA short ROCm test phrase.\n") + [151847, 151848, 151851]
    codec = list(range(64))
    latents = synthesize(model, prefix=prefix, codec=codec, seed=831001, steps=2,
                         attention="sdpa")
    assert latents.shape == (len(codec), 64)
    assert latents.dtype == torch.float32
    assert torch.isfinite(latents).all()
    assert latents.abs().max().item() > 1e-6, "solver returned all-zero latents"


def test_vae_decode_finite(runtime):
    vae = runtime.vae
    torch.manual_seed(11)
    latents = torch.randn(1, 64, 120, device="cuda", dtype=torch.float32)
    audio = vae.decode_tiled(latents, core_frames=64, halo_frames=16, output_device="cpu")
    assert audio.ndim == 3 and audio.shape[0] == 1 and audio.shape[1] == 2
    assert torch.isfinite(audio).all()
    assert audio.abs().max().item() <= 1.0 + 1e-3


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-x", "-s"]))
