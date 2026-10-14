#!/usr/bin/env bash
# Phase 1 mandatory + extended validation of the pinned ROCm PyTorch stack.
# Runs INSIDE environments/yue2-gfx1100. Fails hard on any deviation.
set -euo pipefail
WS="$(cd "$(dirname "$0")/.." && pwd)"
source "$WS/environments/yue2-gfx1100/bin/activate"

echo "=== versions ==="
python - <<'PY'
import torch, torchvision, torchaudio
print("torch =", torch.__version__)
print("torchvision =", torchvision.__version__)
print("torchaudio =", torchaudio.__version__)
print("HIP =", torch.version.hip)
print("CUDA build =", torch.version.cuda)
assert torch.__version__ == "2.12.0+rocm7.14.1"
assert torchvision.__version__ == "0.27.0+rocm7.14.1"
assert torchaudio.__version__ == "2.11.0+rocm7.14.1"
assert torch.version.hip is not None
assert torch.version.cuda is None
assert torch.cuda.is_available()
print("GPU =", torch.cuda.get_device_name(0))
props = torch.cuda.get_device_properties(0)
print("Properties =", props)
assert "gfx1100" in str(getattr(props, "gcnArchName", "")), "Expected gfx1100"
for dtype in (torch.float32, torch.float16, torch.bfloat16):
    a = torch.randn(1024, 1024, device="cuda").to(dtype)
    b = torch.randn(1024, 1024, device="cuda").to(dtype)
    c = a @ b
    torch.cuda.synchronize()
    assert torch.isfinite(c).all()
    print(dtype, "PASS", c.shape)
print("W7900 ROCm PyTorch smoke test PASS")
PY

echo "=== extended: allocator, sync, memory stats, transfers, repeated launches ==="
python - <<'PY'
import torch, json, time
assert torch.cuda.is_available()
# allocator + reset
torch.cuda.empty_cache()
base = torch.cuda.memory_allocated()
x = torch.randn(4096, 4096, device="cuda", dtype=torch.bfloat16)  # 32 MiB
assert torch.cuda.memory_allocated() > base, "allocator stats not tracking"
del x
torch.cuda.synchronize()
# host<->device transfers, both directions, integrity-checked
h = torch.arange(0, 1_000_000, dtype=torch.float64)
d = h.to("cuda", non_blocking=False)
back = d.to("cpu", non_blocking=False)
assert torch.equal(h, back), "H2D/D2H corruption"
torch.cuda.synchronize()
# 50 consecutive small launches (stream health)
s = torch.cuda.current_stream()
t0 = time.time()
acc = torch.zeros(1, device="cuda")
for i in range(50):
    acc += torch.ones(1, device="cuda")
torch.cuda.synchronize()
assert acc.item() == 50.0, f"launch sequence wrong: {acc.item()}"
dt = time.time() - t0
info = {
    "device_count": torch.cuda.device_count(),
    "device_name": torch.cuda.get_device_name(0),
    "gcnArchName": getattr(torch.cuda.get_device_properties(0), "gcnArchName", None),
    "total_mem_GiB": round(torch.cuda.get_device_properties(0).total_memory / 2**30, 2),
    "max_split_ratio?": None,
    "cudnn_available": torch.backends.cudnn.is_available(),
    "peer_visibility": torch.cuda.can_device_access_peer(0, 0) if torch.cuda.device_count() > 1 else "single-device",
    "50_launch_time_ms": round(dt * 1000, 2),
}
print(json.dumps(info, indent=1))
# memory stats present and sane
torch.cuda.reset_peak_memory_stats()
_ = torch.randn(2048, 2048, device="cuda") @ torch.randn(2048, 2048, device="cuda")
torch.cuda.synchronize()
peak = torch.cuda.max_memory_allocated()
assert peak > 0, "peak memory stats broken"
print("peak_memory_allocated_bytes:", peak)
print("EXTENDED PASS")
PY

echo "=== wheel provenance / freeze ==="
python -m pip freeze | grep -Ei 'torch|rocm|triton|numpy|pillow' || true
python -m pip list --format=freeze > "$WS/logs/phase1_pip_freeze.txt"
python - <<'PY'
import importlib.util, json, pathlib
spec = importlib.util.find_spec("torch")
root = pathlib.Path(spec.origin).parent
print("torch package root:", root)
PY
echo "=== which ROCm userspace actually loads ==="
python - <<'PY'
import torch, subprocess
# ldd the torch _C extension and report every roc/amd/hip library source
so = None
import pathlib
for p in pathlib.Path(torch.__file__).parent.rglob("_C*.so"):
    so = p; break
print("_C:", so)
out = subprocess.run(["ldd", str(so)], capture_output=True, text=True).stdout
hits = {}
for line in out.splitlines():
    if "=> /" in line and any(k in line for k in ("rocm", "amd", "hip", "amd_comgr", "hsa", "roc")):
        lib = line.split("=>")[0].strip()
        path = line.split("=>")[1].strip().split()[0]
        hits[lib] = path
for k, v in sorted(hits.items()):
    print(f"{k:30s} {v}")
venv_userspace = sum(1 for v in hits.values() if "environments/yue2-gfx1100" in v)
host_userspace = sum(1 for v in hits.values() if v.startswith("/opt/rocm"))
print(f"venv-provided ROCm libs: {venv_userspace}, host-provided: {host_userspace}")
PY
echo "PHASE1_VALIDATION_ALL_PASS"
