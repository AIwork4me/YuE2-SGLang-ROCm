"""P0.2 GPU smoke test — fresh image, physical gfx1100 validation.

Uses the preinstalled base venv torch first (2.9.1 ROCm). Environment-specific
torch versions get their own smoke runs in Phase P2.
"""
import json
import sys
import time
import traceback

import torch

R = {"python": sys.version.split()[0], "torch": torch.__version__}

def main():
    R["cuda_available"] = torch.cuda.is_available()
    R["torch_cuda_version"] = torch.version.cuda
    R["torch_hip_version"] = torch.version.hip
    R["device_count"] = torch.cuda.device_count()
    if not R["cuda_available"] or R["device_count"] == 0:
        print(json.dumps(R, indent=2))
        sys.exit(2)
    dev = torch.device("cuda:0")
    props = torch.cuda.get_device_properties(0)
    R["gpu_name"] = props.name
    R["gpu_total_mem_bytes"] = props.total_memory
    R["gpu_cc"] = f"{props.major}.{props.minor}"
    R["gpu_gcnarch"] = getattr(props, "gcnArchName", "")
    R["hip_architecture"] = torch.cuda.get_device_capability(0)

    torch.manual_seed(0)
    ok = {}

    # BF16 matmul
    a = torch.randn(4096, 4096, device=dev, dtype=torch.bfloat16)
    b = torch.randn(4096, 4096, device=dev, dtype=torch.bfloat16)
    t0 = time.perf_counter()
    for _ in range(20):
        c = a @ b
    torch.cuda.synchronize()
    R["bf16_matmul_ms"] = round((time.perf_counter() - t0) / 20 * 1000, 3)
    ok["bf16_finite"] = bool(torch.isfinite(c).all().item())

    # FP32 matmul
    a32 = torch.randn(2048, 2048, device=dev, dtype=torch.float32)
    b32 = torch.randn(2048, 2048, device=dev, dtype=torch.float32)
    t0 = time.perf_counter()
    for _ in range(20):
        c32 = a32 @ b32
    torch.cuda.synchronize()
    R["fp32_matmul_ms"] = round((time.perf_counter() - t0) / 20 * 1000, 3)
    # numerical sanity vs CPU on a small slice (corner block of the FULL product)
    ref = (a32[:256, :].cpu() @ b32[:, :256].cpu())
    rel = ((c32[:256, :256].cpu() - ref).abs().max() / ref.abs().max()).item()
    ok["fp32_relerr_small"] = rel < 1e-4
    R["fp32_relerr"] = float(f"{rel:.3e}")

    # SDPA
    q = torch.randn(8, 16, 1024, 64, device=dev, dtype=torch.bfloat16)
    k = torch.randn(8, 16, 1024, 64, device=dev, dtype=torch.bfloat16)
    v = torch.randn(8, 16, 1024, 64, device=dev, dtype=torch.bfloat16)
    with torch.nn.attention.sdpa_kernel(torch.nn.attention.SDPBackend.MATH):
        o1 = torch.nn.functional.scaled_dot_product_attention(q, k, v)
    o2 = torch.nn.functional.scaled_dot_product_attention(q, k, v)  # default backend select
    torch.cuda.synchronize()
    ok["sdpa_math_finite"] = bool(torch.isfinite(o1).all().item())
    ok["sdpa_default_finite"] = bool(torch.isfinite(o2).all().item())
    d = (o1.float() - o2.float()).abs().max().item()
    R["sdpa_math_vs_default_maxdiff"] = float(f"{d:.4f}")

    # memory alloc/release
    free0, total = torch.cuda.mem_get_info()
    nblocks, block_bytes = 8, 512 * 1024 * 1024  # 4 GiB total
    blocks = [torch.empty(block_bytes, device=dev, dtype=torch.uint8) for _ in range(nblocks)]
    free1, _ = torch.cuda.mem_get_info()
    del blocks
    torch.cuda.empty_cache()
    free2, _ = torch.cuda.mem_get_info()
    R["mem_before_gb"] = round((total - free0) / 2**30, 3)
    R["mem_after_alloc_gb"] = round((total - free1) / 2**30, 3)
    R["mem_after_release_gb"] = round((total - free2) / 2**30, 3)
    ok["mem_released"] = (free2 - free1) > (nblocks - 1) * block_bytes  # ≥ 3.5 GiB returned

    # sync + error handling (catch a device-side abort is destructive; use assert check instead)
    x = torch.zeros(1024, device=dev)
    x.add_(1.0)
    torch.cuda.synchronize()
    ok["sync_add"] = bool((x == 1).all().item())

    R["checks"] = ok
    R["overall_pass"] = all(ok.values())
    print(json.dumps(R, indent=2))
    sys.exit(0 if R["overall_pass"] else 1)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        R["exception"] = traceback.format_exc()
        print(json.dumps(R, indent=2))
        sys.exit(3)
