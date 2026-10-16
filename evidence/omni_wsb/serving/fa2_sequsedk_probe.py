#!/usr/bin/env python3
"""fa2_sequsedk_probe.py - Phase 6 ROCm FA2 compatibility probe (isolated env).

Answers, with numerical evidence, whether YuE2's ragged varlen attention
(per-row effective KV length via seqused_k, non-causal, GQA) can safely move
from the validated ATen path to a ROCm flash_attn_2 build.

Tests (each PASS requires max-abs-diff vs float64 reference within tolerance):
  T1  variable sequence lengths across ragged rows
  T2  seqused_k smaller than allocated KV length (padded tail must be ignored)
  T3  padded KV garbage tail (NaN/inf/garbage in the padded region must not
      leak into output when seqused_k caps the row)
  T4  GQA (HQ != HKV)
  T5  non-causal attention
  T6  multiple ragged rows in one packed call
  T7  BF16 and FP16 dtypes
  T8  ATen seqused_k semantics (the CURRENT validated path - baseline)
  T9  flash_attn (FA2) availability + seqused_k forwarding probe (if installed)
  T10 kernel latency microbenchmark (ATen vs FA2-if-available)

Runs entirely in its own process; imports only torch (+ optional flash_attn).
Never writes to any production environment.
"""
from __future__ import annotations

import importlib
import json
import statistics
import sys
import time

import torch

DEV = "cuda"
RESULTS: dict = {"torch": torch.__version__, "hip": torch.version.hip,
                 "device": None, "tests": {}, "latency": {}, "verdicts": {}}


def reference_attn(q, k, v, lens_q, eff_k, scale):
    """float64 CPU reference honoring per-row effective KV lengths."""
    outs = []
    pos_q = 0
    for r in range(len(lens_q)):
        lq = lens_q[r]
        qr = q[pos_q:pos_q + lq].double()          # [lq, HQ, D]
        kr = k[r][:eff_k[r]].double()              # [eff_k, HKV, D]
        vr = v[r][:eff_k[r]].double()
        # GQA by repeating KV heads
        rep = qr.shape[1] // kr.shape[1]
        kr = kr.repeat_interleave(rep, dim=1)
        vr = vr.repeat_interleave(rep, dim=1)
        scores = torch.einsum("qhd,khd->hqk", qr, kr) * scale
        attn = scores.softmax(dim=-1)
        out = torch.einsum("hqk,khd->qhd", attn, vr)
        outs.append(out)
        pos_q += lq
    return torch.cat(outs, dim=0)


def make_case(rows, dtype, seed, hq=8, hkv=4, d=64, pad_to=None):
    g = torch.Generator(device="cpu").manual_seed(seed)
    lens_q = [t for t in rows]
    eff_k = [t + 7 for t in rows]                 # q shorter than k
    alloc = pad_to or max(eff_k) + 29             # allocated KV > effective
    q = torch.randn(sum(lens_q), hq, d, generator=g)
    k = torch.randn(len(rows), alloc, hkv, d, generator=g)
    v = torch.randn(len(rows), alloc, hkv, d, generator=g)
    cu_q = torch.tensor([0] + list(torch.tensor(lens_q).cumsum(0)),
                        dtype=torch.int32)
    cu_k = torch.tensor([i * alloc for i in range(len(rows) + 1)],
                        dtype=torch.int32)
    # packed k/v with per-row allocated rows (cu_seqlens_k = row starts)
    k_packed = k.reshape(-1, hkv, d)
    v_packed = v.reshape(-1, hkv, d)
    seqused = torch.tensor(eff_k, dtype=torch.int32)
    to = {"float64": torch.float64, "float32": torch.float32,
          "bfloat16": torch.bfloat16, "float16": torch.float16}[dtype]
    return (q.to(DEV, to), k_packed.to(DEV, to), v_packed.to(DEV, to),
            cu_q.to(DEV), cu_k.to(DEV), torch.tensor(max(lens_q)),
            torch.tensor(alloc), seqused.to(DEV),
            lens_q, eff_k, alloc, q, k, v)


def aten_varlen(q, k, v, cu_q, cu_k, max_q, max_k, seqused):
    return torch.ops.aten._flash_attention_forward(
        q, k, v, cu_q, cu_k, int(max_q), int(max_k), 0.0, False, False,
        seqused_k=seqused)[0]


def check(name, out, lens_q, eff_k, alloc, q_ref, k_ref, v_ref, scale, tol):
    ref = reference_attn(q_ref, k_ref, v_ref, lens_q, eff_k, scale).to(DEV)
    diff = (out.float() - ref.float()).abs().max().item()
    ok = diff <= tol
    RESULTS["tests"][name] = {"max_abs_diff": diff, "tol": tol, "pass": ok}
    print(f"{name}: max_abs_diff={diff:.3e} tol={tol:.1e} "
          f"{'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def main():
    scale = 1.0 / (64 ** 0.5)
    RESULTS["device"] = torch.cuda.get_device_name(0)
    print("device:", RESULTS["device"], "torch", torch.__version__,
          "hip", torch.version.hip, flush=True)

    ok = True
    # T1 variable lengths / T5 non-causal / T6 multiple ragged rows (bf16:
    # ATen FlashAttention on ROCm accepts fp16/bf16 only, matching YuE2)
    case = make_case([3, 17, 5, 128, 1], "bfloat16", 1)
    q, k, v, cu_q, cu_k, mq, mk, sq, lq, ek, al, qr, kr, vr = case
    out = aten_varlen(q, k, v, cu_q, cu_k, mq, mk, sq)
    ok &= check("T1_variable_len_bf16", out, lq, ek, al, qr, kr, vr, scale, 2e-2)
    # T2 seqused_k < allocated (implicit above: alloc = eff+29) - explicit check
    case = make_case([8, 8], "bfloat16", 2, pad_to=97)
    q, k, v, cu_q, cu_k, mq, mk, sq, lq, ek, al, qr, kr, vr = case
    out = aten_varlen(q, k, v, cu_q, cu_k, mq, mk, sq)
    ok &= check("T2_seqused_lt_alloc_bf16", out, lq, ek, al, qr, kr, vr, scale, 2e-2)
    # T3 garbage tail: poison the padded region; output must be unchanged
    out_clean = out.clone()
    k2 = k.clone()
    for r in range(len(lq)):
        start = r * al + ek[r]
        k2.view(al * len(lq), -1)[start:(r + 1) * al] = float("nan")
    out_p = aten_varlen(q, k2, v, cu_q, cu_k, mq, mk, sq)
    d = (out_p.float() - out_clean.float()).abs().max().item()
    t3 = d == 0.0 or d <= 1e-6
    RESULTS["tests"]["T3_padded_kv_garbage_bf16"] = {"max_abs_diff": d,
                                                     "pass": t3}
    print(f"T3_padded_kv_garbage_bf16: max_abs_diff={d:.3e} "
          f"{'PASS' if t3 else 'FAIL'}", flush=True)
    ok &= t3
    # T4 GQA already exercised (hq=8 hkv=4); single-head KV variant
    case = make_case([16, 33], "bfloat16", 3, hq=8, hkv=1)
    q, k, v, cu_q, cu_k, mq, mk, sq, lq, ek, al, qr, kr, vr = case
    out = aten_varlen(q, k, v, cu_q, cu_k, mq, mk, sq)
    ok &= check("T4_gqa_8to1_bf16", out, lq, ek, al, qr, kr, vr, scale, 2e-2)
    # T7 BF16 / FP16
    for name, dt, tol in (("T7a_bfloat16", "bfloat16", 2e-2),
                          ("T7b_float16", "float16", 2e-2)):
        case = make_case([5, 64, 12], dt, 4)
        q, k, v, cu_q, cu_k, mq, mk, sq, lq, ek, al, qr, kr, vr = case
        out = aten_varlen(q, k, v, cu_q, cu_k, mq, mk, sq)
        ok &= check(f"{name}_seqused", out, lq, ek, al, qr, kr, vr, scale, tol)

    # T8 ATen WITHOUT seqused_k over the same packed layout must differ
    # (proves seqused_k is actually honored in T2, not a no-op)
    case = make_case([8, 8], "bfloat16", 2, pad_to=97)
    q, k, v, cu_q, cu_k, mq, mk, sq, lq, ek, al, qr, kr, vr = case
    out_no = aten_varlen(q, k, v, cu_q, cu_k, mq, mk, None)
    ref = reference_attn(qr, kr, vr, lq, ek, 1.0 / 8).to(DEV)
    d_no = (out_no.float() - ref.float()).abs().max().item()
    honored = d_no > 1e-3
    RESULTS["tests"]["T8_seqused_honored_control"] = {
        "diff_vs_capped_ref_without_seqused": d_no, "pass": honored}
    print(f"T8_seqused_honored_control: diff={d_no:.3e} "
          f"{'PASS (seqused_k changes result as expected)' if honored else 'FAIL'}",
          flush=True)
    ok &= honored

    # T9 flash_attn FA2 availability probe
    fa = None
    try:
        fa = importlib.import_module("flash_attn")
        RESULTS["flash_attn"] = getattr(fa, "__version__", "unknown")
    except Exception as e:
        RESULTS["flash_attn"] = f"unavailable: {type(e).__name__}"
    if fa is not None:
        try:
            import inspect
            sig = inspect.signature(fa.flash_attn_varlen_func)
            has_sq = "seqused_k" in sig.parameters
            RESULTS["fa2_varlen_has_seqused_k_param"] = has_sq
            case = make_case([8, 8], "float16", 5)
            q, k, v, cu_q, cu_k, mq, mk, sq, lq, ek, al, qr, kr, vr = case
            kw = {"seqused_k": sq} if has_sq else {}
            out = fa.flash_attn_varlen_func(
                q, k, v, cu_q, cu_k, int(mq), al,
                softmax_scale=scale, causal=False, **kw)
            if has_sq:
                ok &= check("T9_fa2_seqused_fp16", out, lq, ek, al,
                            qr, kr, vr, scale, 2e-2)
            else:
                # without seqused_k support, FA2 can only be correct if the
                # caller re-packs K/V to effective lengths (path A)
                RESULTS["verdicts"]["fa2_direct"] = (
                    "BLOCKED: public varlen API lacks seqused_k; requires KV "
                    "repacking to effective lengths before call")
        except Exception as e:
            RESULTS["verdicts"]["fa2_direct"] = (
                f"BLOCKED: {type(e).__name__}: {e}"[:300])

    # T10 latency: ATen varlen, YuE2-AR-like shape (bs rows ~1..4, long KV)
    for tag, rows, alloc in (("small_kv", [1, 1, 2, 4], 4096),
                             ("long_kv", [1, 1], 16384)):
        case = make_case(rows, "bfloat16", 6, pad_to=alloc)
        q, k, v, cu_q, cu_k, mq, mk, sq, *_ = case
        for _ in range(5):
            aten_varlen(q, k, v, cu_q, cu_k, mq, mk, sq)
        torch.cuda.synchronize()
        ts = []
        for _ in range(50):
            t0 = time.perf_counter()
            aten_varlen(q, k, v, cu_q, cu_k, mq, mk, sq)
            torch.cuda.synchronize()
            ts.append(time.perf_counter() - t0)
        RESULTS["latency"][f"aten_{tag}"] = {
            "p50_ms": round(statistics.median(ts) * 1e3, 3),
            "mean_ms": round(statistics.mean(ts) * 1e3, 3)}
        print(f"latency aten {tag}: p50={statistics.median(ts)*1e3:.3f}ms",
              flush=True)

    RESULTS["verdicts"]["aten_path"] = "PASS" if ok else "FAIL"
    RESULTS["overall_pass"] = bool(ok)
    out_path = sys.argv[1] if len(sys.argv) > 1 else "fa2_probe_results.json"
    with open(out_path, "w") as f:
        json.dump(RESULTS, f, indent=2)
    print("OVERALL:", "PASS" if ok else "FAIL", "->", out_path, flush=True)


if __name__ == "__main__":
    main()
