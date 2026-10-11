"""Phase 0 GPU smoke test: basic FP32/FP16/BF16 compute on gfx1151."""
import json
import sys

result = {"ok": True, "errors": []}

import torch

print(f"torch.__version__ = {torch.__version__}")
print(f"torch.version.hip = {torch.version.hip}")
print(f"torch.cuda.is_available() = {torch.cuda.is_available()}")
result["torch_version"] = torch.__version__
result["torch_hip"] = torch.version.hip
result["cuda_available"] = torch.cuda.is_available()

assert torch.cuda.is_available(), "torch.cuda.is_available() is False"
print(f"device_count = {torch.cuda.device_count()}")
print(f"device 0 name = {torch.cuda.get_device_name(0)}")
result["device_name"] = torch.cuda.get_device_name(0)
caps = torch.cuda.get_device_capability(0)
print(f"device capability (arch) = {caps}")
result["gcn_arch_name"] = torch.cuda.get_device_properties(0).gcnArchName

props = torch.cuda.get_device_properties(0)
result["total_memory_gb"] = props.total_memory / 1024**3
print(f"reported total GPU memory = {props.total_memory/1024**3:.2f} GiB")

ref = torch.arange(0, 64, dtype=torch.float32, device="cuda") * 0.5
for dt, name in [(torch.float32, "fp32"), (torch.float16, "fp16"), (torch.bfloat16, "bf16")]:
    try:
        a = (torch.randn(1024, 1024, device="cuda", dtype=torch.float32) * 0.1).to(dt)
        b = (torch.randn(1024, 1024, device="cuda", dtype=torch.float32) * 0.1).to(dt)
        c = (a @ b).float()
        torch.cuda.synchronize()
        finite = bool(torch.isfinite(c).all().item())
        # correctness: compare vs fp32 reference computed on GPU
        a32, b32 = a.float(), b.float()
        c32 = a32 @ b32
        err = (c - c32).abs().max().item()
        print(f"{name}: matmul OK, finite={finite}, max|diff vs fp32|={err:.3e}")
        result[name] = {"finite": finite, "max_abs_err_vs_fp32": err}
        if not finite:
            result["ok"] = False
            result["errors"].append(f"{name} non-finite output")
    except Exception as e:
        result["ok"] = False
        result["errors"].append(f"{name}: {type(e).__name__}: {e}")
        print(f"{name}: FAILED {e}")

peak = torch.cuda.max_memory_allocated() / 1024**2
print(f"peak allocated GPU memory during test = {peak:.1f} MiB")
result["peak_alloc_mib"] = peak

import os
out = os.environ.get("WS", "/home/amd/Desktop/YuE2") + "/logs/phase0_gpu_smoke.json"
with open(out, "w") as f:
    json.dump(result, f, indent=2)

print("SMOKE_RESULT:", "PASS" if result["ok"] else "FAIL")
sys.exit(0 if result["ok"] else 1)
