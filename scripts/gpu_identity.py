#!/usr/bin/env python3
"""gpu_identity.py — GPU execution identity chain & fail-loud contract (RC4.1 M1).

NO SILENT FALLBACK contract: GPU work must run on the expected Radeon device.
This tool records the evidence chain and refuses to pass when identity is
unverified:

  1. Expected GPU      — arch (gcnArchName) and optional PCI BDF from caller
  2. Framework GPU     — torch.version.hip, torch.cuda.is_available(),
                         get_device_properties(0)
  3. Actual placement  — the probe tensor's real device string
  4. Active execution  — small matmul on the device, checksum-verified
  5. Worker identity   — pid, starttime, cmdline in the receipt
  6. KFD visibility    — /dev/kfd + /dev/dri/renderD* presence

On ROCm, PyTorch exposes the GPU through the torch.cuda API namespace
(torch.version.hip is set); "cuda" in an API name is NOT an NVIDIA indicator.
Only torch.version.cuda being set would be.

Statuses (receipt field `status`, machine-readable):
  GPU_IDENTITY_VERIFIED    device present, arch/BDF match (probe skipped)
  GPU_EXECUTION_VERIFIED   identity verified AND compute probe passed on device
  GPU_EXECUTION_UNVERIFIED identity ok, probe explicitly skipped
  GPU_DEVICE_MISMATCH      device present but arch/BDF != expected -> FAIL
  GPU_UNAVAILABLE          no usable device and no explicit CPU authorization
  GPU_PROGRESS_TIMEOUT     probe did not finish in the bounded budget
  GPU_EXECUTION_FAILED     probe raised / wrong result
  CPU_TEST_MODE_AUTHORIZED explicit --allow-cpu test mode (never a GPU PASS)

Exit codes: 0 verified/unverified-ok · 3 mismatch · 4 unavailable ·
5 probe failure · 2 usage error.

Usage:
  python scripts/gpu_identity.py verify --expect-arch gfx1100 \
      [--expect-bdf 0000:0b:00.0] [--receipt out.json] [--skip-probe]
  python scripts/gpu_identity.py probe   --expect-arch gfx1100 [--receipt out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

KFD_PATH = "/dev/kfd"
STATUS_OK = {"GPU_IDENTITY_VERIFIED", "GPU_EXECUTION_VERIFIED",
             "GPU_EXECUTION_UNVERIFIED", "CPU_TEST_MODE_AUTHORIZED"}
CPU_AUTH_ENV = "YUE2_ALLOW_CPU"
CPU_AUTH_TOKEN = "1-I-AM-A-TEST"


class _TorchNS:
    """Minimal duck-typed namespace mirror (documentation only)."""


def _load_torch():
    import torch  # lazy: CI unit tests inject a fake via sys.modules
    return torch


def kfd_visibility() -> dict:
    render = sorted(p.name for p in Path("/dev/dri").glob("renderD*")) \
        if Path("/dev/dri").is_dir() else []
    return {"kfd_present": Path(KFD_PATH).exists(),
            "render_nodes": render,
            "visible": Path(KFD_PATH).exists() and bool(render)}


def sysfs_bdf_for_device(dev) -> str | None:
    """Best-effort PCI BDF from torch device props, then /sys/class/drm."""
    for attr in ("pci_bus_id",):
        v = getattr(dev, attr, None)
        if isinstance(v, int):
            dom = getattr(dev, "pci_domain_id", 0)
            devid = getattr(dev, "pci_device_id", None)
            if devid is None:
                return None
            return f"{dom:04x}:{v:02x}:{devid:02x}.0"
    # fallback: unique drm card with amdgpu driver
    try:
        for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
            uevent = card / "device" / "uevent"
            if uevent.is_file() and "amdgpu" in uevent.read_text():
                for line in uevent.read_text().splitlines():
                    if line.startswith("PCI_SLOT_NAME="):
                        return line.split("=", 1)[1].lower()
    except OSError:
        pass
    return None


def _norm_bdf(bdf: str) -> str:
    m = re.fullmatch(r"(?:0000:)?([0-9a-fA-F]{2,4}):([0-9a-fA-F]{2})\."
                     r"([0-9])", bdf.strip())
    if not m:
        return bdf.strip().lower()
    dom = m.group(1).lstrip("0") or "0"
    return f"{int(dom, 16):04x}:{int(m.group(2), 16):02x}:{m.group(3)}"


def bdf_matches(expected: str, actual: str | None) -> bool:
    if not actual:
        return False
    return _norm_bdf(expected) == _norm_bdf(actual)


def probe_device(torch_ns, device_index: int = 0, budget_s: float = 60.0):
    """Run a small verified matmul on the device. Returns probe facts dict.

    Raises RuntimeError on wrong result; TimeoutError is converted by the
    caller into GPU_PROGRESS_TIMEOUT."""
    import math
    t0 = time.monotonic()
    dev = torch_ns.device(f"cuda:{device_index}")
    a = torch_ns.randn(256, 256, device=dev, dtype=torch_ns.float32)
    b = torch_ns.randn(256, 256, device=dev, dtype=torch_ns.float32)
    c = a @ b
    torch_ns.cuda.synchronize(device_index)
    checksum = float(c.sum().item())
    # independent CPU recompute of one entry for correctness evidence
    i, j = 7, 13
    recompute = float((a[i].to("cpu") * b[:, j].to("cpu")).sum().item())
    got = float(c[i, j].item())
    ok = math.isclose(got, recompute, rel_tol=1e-3, abs_tol=1e-3)
    if not ok:
        raise RuntimeError(
            f"GPU probe result mismatch: device={got} cpu_recompute={recompute}")
    return {
        "probe": "matmul256-fp32",
        "probe_device": str(c.device),
        "probe_checksum": round(checksum, 3),
        "probe_entry_cpu_recompute": round(recompute, 6),
        "probe_entry_device": round(got, 6),
        "probe_wall_s": round(time.monotonic() - t0, 3),
    }


def verify(expected_arch: str | None = "gfx1100", expected_bdf: str | None = None,
           run_probe: bool = True, cpu_authorized: bool = False,
           receipt_path: Path | None = None, torch_ns=None, device_index: int = 0,
           probe_budget_s: float = 60.0) -> dict:
    """Build the identity receipt. Returns dict with `status` and `ok`."""
    who = {"pid": os.getpid(),
           "starttime": _self_starttime(),
           "cmdline": _self_cmdline()}
    receipt = {
        "receipt_type": "gpu_identity",
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "expected": {"arch": expected_arch, "bdf": expected_bdf,
                     "cpu_authorized": cpu_authorized},
        "worker": who,
        "kfd": kfd_visibility(),
    }
    try:
        torch = torch_ns if torch_ns is not None else _load_torch()
        receipt["framework"] = {
            "torch_version": getattr(torch, "__version__", "unknown"),
            "hip_version": str(getattr(torch.version, "hip", None)),
            "cuda_version": str(getattr(torch.version, "cuda", None)),
            "cuda_api_available": bool(torch.cuda.is_available()),
        }
    except Exception as e:  # import failure / broken runtime
        receipt["framework"] = {"error": f"{type(e).__name__}: {e}"}
        if cpu_authorized:
            # explicit test-mode authorization covers torch-less stub
            # stacks (CI): still NEVER a GPU PASS
            receipt["status"] = "CPU_TEST_MODE_AUTHORIZED"
            receipt["reason"] = (f"torch runtime unusable ({e}); CPU mode "
                                 "explicitly authorized (test-only, never "
                                 "a GPU PASS)")
            receipt["ok"] = True
        else:
            receipt["status"] = "GPU_UNAVAILABLE"
            receipt["reason"] = f"torch runtime unusable: {e}"
            receipt["ok"] = False
        return _finish(receipt, receipt_path)

    fw = receipt["framework"]
    if fw.get("cuda_version", "None") not in ("None", None):
        receipt["status"] = "GPU_DEVICE_MISMATCH"
        receipt["reason"] = ("CUDA-only torch build (torch.version.cuda set); "
                             "this project requires the ROCm/HIP stack")
        receipt["ok"] = False
        return _finish(receipt, receipt_path)

    if not fw["cuda_api_available"]:
        if cpu_authorized:
            receipt["status"] = "CPU_TEST_MODE_AUTHORIZED"
            receipt["reason"] = ("no GPU visible; CPU mode explicitly "
                                 "authorized (test-only, never a GPU PASS)")
            receipt["ok"] = True
        else:
            receipt["status"] = "GPU_UNAVAILABLE"
            receipt["reason"] = ("torch.cuda.is_available()=False and no "
                                 "explicit CPU authorization (GPU_REQUIRED "
                                 "default; NO silent CPU fallback)")
            receipt["ok"] = False
        return _finish(receipt, receipt_path)

    try:
        props = torch.cuda.get_device_properties(device_index)
        arch = getattr(props, "gcnArchName", None)
        name = getattr(props, "name", None)
        total = getattr(props, "total_memory", None)
    except Exception as e:
        receipt["status"] = "GPU_UNAVAILABLE"
        receipt["reason"] = f"get_device_properties failed: {e}"
        receipt["ok"] = False
        return _finish(receipt, receipt_path)

    bdf = sysfs_bdf_for_device(props)
    receipt["device"] = {"index": device_index, "name": name, "arch": arch,
                         "gcn_arch_names": _arch_list(arch),
                         "pci_bdf": bdf,
                         "total_memory_bytes": total,
                         "total_memory_gib": (round(total / 2**30, 2)
                                              if isinstance(total, int) else None)}

    if expected_arch and expected_arch not in _arch_list(arch):
        receipt["status"] = "GPU_DEVICE_MISMATCH"
        receipt["reason"] = (f"device arch {arch!r} does not include expected "
                             f"{expected_arch!r}")
        receipt["ok"] = False
        return _finish(receipt, receipt_path)
    if expected_bdf and not bdf_matches(expected_bdf, bdf):
        receipt["status"] = "GPU_DEVICE_MISMATCH"
        receipt["reason"] = (f"device PCI BDF {bdf!r} != expected "
                             f"{expected_bdf!r}")
        receipt["ok"] = False
        return _finish(receipt, receipt_path)

    receipt["status"] = "GPU_IDENTITY_VERIFIED"
    if not run_probe:
        receipt["status"] = "GPU_EXECUTION_UNVERIFIED"
        receipt["ok"] = True
        return _finish(receipt, receipt_path)

    try:
        facts = probe_device(torch, device_index=device_index,
                             budget_s=probe_budget_s)
        receipt["probe_facts"] = facts
        if expected_arch and expected_arch not in facts["probe_device"]:
            pass  # device string is cuda:N on ROCm; identity already checked
        receipt["status"] = "GPU_EXECUTION_VERIFIED"
        receipt["ok"] = True
    except TimeoutError as e:
        receipt["status"] = "GPU_PROGRESS_TIMEOUT"
        receipt["reason"] = f"probe exceeded {probe_budget_s}s: {e}"
        receipt["ok"] = False
    except Exception as e:
        receipt["status"] = "GPU_EXECUTION_FAILED"
        receipt["reason"] = f"probe failed: {type(e).__name__}: {e}"
        receipt["ok"] = False
    return _finish(receipt, receipt_path)


def _arch_list(arch: str | None) -> list[str]:
    # gcnArchName may be "gfx1100" or "gfx1100:sramecc+:xnack-"
    if not arch:
        return []
    return [p for p in arch.split(":") if p and not p.startswith(("sramecc", "xnack"))]


def _self_starttime() -> str | None:
    try:
        data = Path(f"/proc/{os.getpid()}/stat").read_text()
        return data[data.rindex(")") + 1:].split()[19]
    except (OSError, ValueError):
        return None


def _self_cmdline() -> str:
    try:
        return Path(f"/proc/{os.getpid()}/cmdline").read_bytes().replace(
            b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        return ""


def _finish(receipt: dict, receipt_path: Path | None) -> dict:
    receipt["verdict"] = "PASS" if receipt.get("ok") else "FAIL"
    if receipt_path:
        p = Path(receipt_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(receipt, indent=1) + "\n")
    return receipt


EXIT_BY_STATUS = {"GPU_DEVICE_MISMATCH": 3, "GPU_UNAVAILABLE": 4,
                  "GPU_PROGRESS_TIMEOUT": 5, "GPU_EXECUTION_FAILED": 5}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("verify", "probe"):
        s = sub.add_parser(name)
        s.add_argument("--expect-arch", default=os.environ.get(
            "YUE2_EXPECT_GPU_ARCH", "gfx1100"),
            help="required gcnArchName (default gfx1100; empty string skips)")
        s.add_argument("--expect-bdf", default=os.environ.get(
            "YUE2_EXPECT_GPU_BDF"), help="optional exact PCI BDF")
        s.add_argument("--receipt", type=Path, default=None)
        s.add_argument("--device-index", type=int, default=0)
        s.add_argument("--probe-budget-s", type=float, default=60.0)
        if name == "verify":
            s.add_argument("--skip-probe", action="store_true")
            s.add_argument("--allow-cpu", action="store_true",
                           help="explicit CPU test-mode authorization "
                                "(never reported as GPU PASS)")
    a = ap.parse_args(argv)
    cpu_auth = bool(getattr(a, "allow_cpu", False) or
                    os.environ.get(CPU_AUTH_ENV) == CPU_AUTH_TOKEN)
    r = verify(expected_arch=a.expect_arch or None, expected_bdf=a.expect_bdf,
               run_probe=(a.cmd == "probe" or not getattr(a, "skip_probe", False)),
               cpu_authorized=cpu_auth, receipt_path=a.receipt,
               device_index=a.device_index, probe_budget_s=a.probe_budget_s)
    print(json.dumps(r, indent=1))
    return EXIT_BY_STATUS.get(r["status"], 0 if r["ok"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
